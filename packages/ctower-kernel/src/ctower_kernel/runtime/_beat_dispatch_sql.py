"""Operator reads for immutable fleet-beat routines and emitted effects."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor
from ctower_kernel.runtime import OccurrenceOutcome, OccurrencePlan, RoutineRevision
from ctower_kernel.runtime._routine_ids import stable_uuid7
from ctower_kernel.runtime.beats import BeatDispatchEffect, BeatDispatchSpec, BeatRoutine
from ctower_kernel.runtime.gates import ActivityGate

__all__: tuple[str, ...] = ()


def register_spec(
    connection: psycopg.Connection[dict[str, object]], revision: RoutineRevision
) -> None:
    spec = revision.beat_dispatch
    if spec is None:
        return
    connection.execute(
        """
        INSERT INTO routine_beat_dispatch_specs (
            revision_digest, beat_key, prompt_source, prompt_sha256, prompt, target_session
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (revision_digest) DO NOTHING
        """,
        (
            _digest_bytes(revision.revision_digest),
            spec.beat_key,
            spec.prompt_source,
            _digest_bytes(spec.prompt_sha256),
            spec.prompt,
            spec.target_session,
        ),
    )


def insert_effect(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    occurrence_id: UUID,
    revision: RoutineRevision,
    plan: OccurrencePlan,
    now: datetime,
) -> BeatDispatchEffect | None:
    spec = revision.beat_dispatch
    if spec is None or plan.outcome is not OccurrenceOutcome.QUEUED:
        return None
    effect_id = stable_uuid7(
        plan.scheduled_for,
        b"beat-dispatch",
        tenant_id.bytes,
        _digest_bytes(revision.revision_digest),
        plan.scheduled_for.isoformat().encode("ascii"),
    )
    connection.execute(
        """
        INSERT INTO runtime_beat_dispatch_effects (
            effect_id, occurrence_id, tenant_id, revision_digest, routine_ref,
            scheduled_for, beat_key, prompt_source, prompt_sha256, prompt,
            target_session, emitted_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            effect_id,
            occurrence_id,
            tenant_id,
            _digest_bytes(revision.revision_digest),
            revision.routine_ref,
            plan.scheduled_for,
            spec.beat_key,
            spec.prompt_source,
            _digest_bytes(spec.prompt_sha256),
            spec.prompt,
            spec.target_session,
            now,
        ),
    )
    return BeatDispatchEffect(
        effect_id=effect_id,
        occurrence_id=occurrence_id,
        tenant_id=tenant_id,
        routine_ref=revision.routine_ref,
        revision_digest=revision.revision_digest,
        scheduled_for=plan.scheduled_for,
        spec=spec,
        emitted_at=now,
    )


def list_beat_dispatches(dsn: str, actor: Actor) -> tuple[BeatDispatchEffect, ...]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        rows = connection.execute(
            """
            SELECT effect.*
            FROM runtime_beat_dispatch_effects AS effect
            WHERE effect.tenant_id = %s
              AND EXISTS (
                  SELECT 1 FROM principals AS principal
                  WHERE principal.tenant_id = %s
                    AND principal.principal_id = %s
                    AND principal.kind = 'operator'
              )
            ORDER BY effect.scheduled_for, effect.effect_id
            """,
            (actor.tenant_id, actor.tenant_id, actor.principal_id),
        ).fetchall()
    return tuple(_effect(row) for row in rows)


def list_beat_routines(dsn: str, actor: Actor) -> tuple[BeatRoutine, ...]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        rows = connection.execute(
            """
            SELECT revision.routine_ref, revision.revision_digest, revision.timezone,
                revision.schedule_minutes, revision.schedule_hours,
                spec.beat_key, spec.prompt_source, spec.prompt_sha256,
                spec.target_session, trigger.next_fire_at,
                gate.gate_kind, gate.gate_source, gate.gate_threshold, gate.gate_project_key
            FROM routine_triggers AS trigger
            JOIN routine_revisions AS revision
              ON revision.revision_digest = trigger.revision_digest
            JOIN routine_beat_dispatch_specs AS spec
              ON spec.revision_digest = revision.revision_digest
            LEFT JOIN routine_activity_gates AS gate
              ON gate.revision_digest = revision.revision_digest
            WHERE trigger.tenant_id = %s
              AND EXISTS (
                  SELECT 1 FROM principals AS principal
                  WHERE principal.tenant_id = %s
                    AND principal.principal_id = %s
                    AND principal.kind = 'operator'
              )
            ORDER BY revision.routine_ref
            """,
            (actor.tenant_id, actor.tenant_id, actor.principal_id),
        ).fetchall()
    return tuple(
        BeatRoutine(
            routine_ref=str(row["routine_ref"]),
            revision_digest=_digest(cast(bytes, row["revision_digest"])),
            timezone=str(row["timezone"]),
            minute_marks=tuple(cast(list[int], row["schedule_minutes"])),
            hour_marks=(
                tuple(cast(list[int], row["schedule_hours"]))
                if row["schedule_hours"] is not None
                else None
            ),
            beat_key=str(row["beat_key"]),
            prompt_source=str(row["prompt_source"]),
            prompt_sha256=_digest(cast(bytes, row["prompt_sha256"])),
            target_session=str(row["target_session"]),
            next_fire_at=cast(datetime, row["next_fire_at"]),
            activity_gate=(
                ActivityGate(
                    kind=str(row["gate_kind"]),
                    source=cast(str | None, row["gate_source"]),
                    threshold=cast(int | None, row["gate_threshold"]),
                    project_key=cast(str | None, row["gate_project_key"]),
                )
                if row.get("gate_kind") is not None
                else None
            ),
        )
        for row in rows
    )


def _effect(row: dict[str, object]) -> BeatDispatchEffect:
    spec = BeatDispatchSpec(
        beat_key=str(row["beat_key"]),
        prompt_source=str(row["prompt_source"]),
        prompt_sha256=_digest(cast(bytes, row["prompt_sha256"])),
        prompt=str(row["prompt"]),
        target_session=str(row["target_session"]),
    )
    return BeatDispatchEffect(
        effect_id=cast(UUID, row["effect_id"]),
        occurrence_id=cast(UUID, row["occurrence_id"]),
        tenant_id=cast(UUID, row["tenant_id"]),
        routine_ref=str(row["routine_ref"]),
        revision_digest=_digest(cast(bytes, row["revision_digest"])),
        scheduled_for=cast(datetime, row["scheduled_for"]),
        spec=spec,
        emitted_at=cast(datetime, row["emitted_at"]),
    )


def _digest(value: bytes) -> str:
    return "sha256:" + value.hex()


def _digest_bytes(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("sha256:"))
