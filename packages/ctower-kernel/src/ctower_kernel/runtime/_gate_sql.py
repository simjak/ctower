"""Gate reads, evaluation-fact persistence, and named watermark advance."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.runtime import OccurrenceOutcome, OccurrencePlan, RoutineRevision
from ctower_kernel.runtime._routine_ids import stable_uuid7 as _stable_uuid7
from ctower_kernel.runtime.gates import ActivityGate, GateDecision, GateOutcome, evaluate_gate

__all__: tuple[str, ...] = ()


def apply_gate_decisions(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision: RoutineRevision,
    plans: tuple[OccurrencePlan, ...],
    now: datetime,
) -> tuple[OccurrencePlan, ...]:
    """Evaluate the revision's gate once per scan on the newest due instant.

    Catch-up already collapsed the due prefix; the gate decides whether the
    one occurrence that would queue actually fires. A false or degraded gate
    forces every non-skipped plan to a visible skipped outcome; a true gate
    leaves the catch-up plan untouched. A failed read degrades the evaluation
    to a typed skipped plan with no clean fire.
    """

    if revision.activity_gate is None or not plans:
        return plans
    newest = max(plans, key=lambda plan: plan.scheduled_for)
    decision = evaluate_and_record(connection, tenant_id, revision, newest.scheduled_for, now)
    if decision.outcome.value == "fired":
        return plans
    return tuple(
        OccurrencePlan(
            scheduled_for=plan.scheduled_for,
            local_civil_time=plan.local_civil_time,
            utc_offset_seconds=plan.utc_offset_seconds,
            offset_decision=plan.offset_decision,
            outcome=OccurrenceOutcome.SKIPPED,
        )
        if plan.outcome is not OccurrenceOutcome.SKIPPED
        else plan
        for plan in plans
    )


def activity_gate_from_row(row: dict[str, object]) -> ActivityGate | None:
    if row.get("gate_kind") is None:
        return None
    return ActivityGate(
        kind=str(row["gate_kind"]),
        source=cast(str | None, row["gate_source"]),
        threshold=cast(int | None, row["gate_threshold"]),
        project_key=cast(str | None, row["gate_project_key"]),
    )


def register_gate(
    connection: psycopg.Connection[dict[str, object]], revision: RoutineRevision
) -> None:
    """Persist the revision's typed gate as an immutable registration fact."""

    gate = revision.activity_gate
    if gate is None:
        return
    connection.execute(
        """
        INSERT INTO routine_activity_gates (
            revision_digest, gate_kind, gate_source, gate_threshold, gate_project_key
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (revision_digest) DO NOTHING
        """,
        (
            _digest_bytes(revision.revision_digest),
            gate.kind,
            gate.source,
            gate.threshold,
            gate.project_key,
        ),
    )


def evaluate_and_record(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision: RoutineRevision,
    scheduled_for: datetime,
    now: datetime,
) -> GateDecision:
    """Evaluate one due occurrence's gate and append its typed fact.

    The evaluation fact carries a deterministic identity keyed by the unique
    due instant so an exact replay appends nothing. The named watermark
    advances only when the evaluation actually observed its read.
    """

    gate = revision.activity_gate
    if gate is None:
        return GateDecision(GateOutcome.FIRED, "none", None, 0, "ungated routine")
    revision_digest = _digest_bytes(revision.revision_digest)
    evaluation_id = _stable_uuid7(
        scheduled_for,
        b"gate-evaluation",
        tenant_id.bytes,
        revision_digest,
        scheduled_for.isoformat().encode("ascii"),
    )
    existing = connection.execute(
        """
        SELECT result, watermark_kind, watermark_position, observed_count, detail
        FROM routine_gate_evaluations
        WHERE tenant_id = %s AND revision_digest = %s AND scheduled_for = %s
        """,
        (tenant_id, revision_digest, scheduled_for),
    ).fetchone()
    if existing is not None:
        return GateDecision(
            outcome=GateOutcome(str(existing["result"])),
            watermark_kind=str(existing["watermark_kind"]),
            watermark_position=cast(datetime | None, existing["watermark_position"]),
            observed_count=int(cast(int, existing["observed_count"])),
            detail=str(existing["detail"]),
        )
    watermark = _watermark(connection, tenant_id, revision_digest, gate)
    observed = _observe(connection, tenant_id, gate, watermark)
    decision = evaluate_gate(
        gate,
        now=now,
        due=scheduled_for,
        observed=observed,
        watermark_position=watermark,
    )
    connection.execute(
        """
        INSERT INTO routine_gate_evaluations (
            evaluation_id, tenant_id, revision_digest, scheduled_for, gate_kind,
            result, watermark_kind, watermark_position, observed_count, detail,
            evaluated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, revision_digest, scheduled_for) DO NOTHING
        """,
        (
            evaluation_id,
            tenant_id,
            revision_digest,
            scheduled_for,
            gate.kind,
            decision.outcome.value,
            decision.watermark_kind,
            decision.watermark_position,
            decision.observed_count,
            decision.detail,
            now,
        ),
    )
    if decision.outcome is not GateOutcome.DEGRADED:
        _advance_watermark(connection, tenant_id, revision_digest, gate, now)
    return decision


def _watermark(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision_digest: bytes,
    gate: ActivityGate,
) -> datetime | None:
    row = connection.execute(
        """
        SELECT watermark_position AS value FROM routine_gate_watermarks
        WHERE tenant_id = %s AND revision_digest = %s AND watermark_kind = %s
        """,
        (tenant_id, revision_digest, gate.watermark_kind()),
    ).fetchone()
    if row is None:
        return None
    return cast(datetime, row["value"])


def _advance_watermark(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    revision_digest: bytes,
    gate: ActivityGate,
    now: datetime,
) -> None:
    if gate.kind == "always":
        return
    connection.execute(
        """
        INSERT INTO routine_gate_watermarks (
            tenant_id, revision_digest, watermark_kind, watermark_position, updated_at
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, revision_digest, watermark_kind) DO UPDATE SET
            watermark_position = EXCLUDED.watermark_position,
            updated_at = EXCLUDED.updated_at
        """,
        (tenant_id, revision_digest, gate.watermark_kind(), now, now),
    )


def _observe(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    gate: ActivityGate,
    watermark: datetime | None,
) -> int | None:
    """Run the gate's one canonical read; None means the read itself failed."""

    if gate.kind == "always":
        return 0
    try:
        connection.execute("SAVEPOINT gate_read")
        if gate.kind == "new_movement_since_watermark":
            if watermark is None:
                row = connection.execute(
                    """
                    SELECT count(*) AS value FROM events WHERE tenant_id = %s
                    """,
                    (tenant_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT count(*) AS value FROM events
                    WHERE tenant_id = %s AND server_time > %s
                    """,
                    (tenant_id, watermark),
                ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT count(*) AS value FROM tickets AS ticket
                JOIN lifecycle_episodes AS episode
                  ON episode.tenant_id = ticket.tenant_id
                 AND episode.ticket_id = ticket.ticket_id
                 AND episode.episode_number = ticket.current_episode
                WHERE ticket.tenant_id = %s
                  AND episode.state IN ('open', 'active', 'waiting', 'reopened')
                  AND (%s::text IS NULL OR ticket.project_key = %s)
                """,
                (tenant_id, gate.project_key, gate.project_key),
            ).fetchone()
        connection.execute("RELEASE SAVEPOINT gate_read")
    except psycopg.errors.InsufficientPrivilege:
        connection.execute("ROLLBACK TO SAVEPOINT gate_read")
        return None
    if row is None:
        return None
    return int(cast(int, row["value"]))


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))
