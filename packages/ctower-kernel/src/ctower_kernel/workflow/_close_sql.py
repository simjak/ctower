"""Atomic proof-gated Workflow close behind the Workflow Interface."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import RecordProblem
from ctower_kernel.record.transaction import RecordTransaction
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.workflow import (
    ActivityClass,
    ResolveClose,
    Workflow,
    WorkflowActor,
    WorkflowReceipt,
)
from ctower_kernel.workflow._event_sql import append_change
from ctower_kernel.workflow._postgres_sql import ProofGate

__all__: tuple[str, ...] = ()


def close_workflow(
    dsn: str,
    evaluator: Workflow,
    proof_gate: ProofGate,
    actor: WorkflowActor,
    command: ResolveClose,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkflowReceipt | RecordProblem:
    """Append resolved and closed only after one transactional proof recheck."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        existing = RecordTransaction(connection).reserve(
            actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _receipt(existing)
        if not _lock_open_ticket(connection, actor, command.ticket_id):
            return _problem(command, "tenant-scope-denied", 404, "Open ticket not found")
        run = _lock_run(connection, actor, command.ticket_id)
        refusal = _refusal(evaluator, proof_gate, actor, command, run, connection)
        if refusal is not None:
            return refusal
        _insert_lifecycle(connection, actor, command, now=now)
        receipt = _closed_receipt(cast(dict[str, object], run), command)
        return append_change(
            connection,
            actor,
            command.client_command_id,
            receipt,
            operation="resolve_close",
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _lock_open_ticket(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    ticket_id: UUID,
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM tickets AS t
        JOIN lifecycle_episodes AS episode
          ON episode.tenant_id = t.tenant_id AND episode.ticket_id = t.ticket_id
         AND episode.episode_number = t.current_episode
        WHERE t.tenant_id = %s AND t.ticket_id = %s
          AND episode.state NOT IN ('closed', 'cancelled')
        FOR UPDATE
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()
    return row is not None


def _lock_run(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    ticket_id: UUID,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT workflow_run_id, workflow_key, workflow_revision, current_stage,
            activity_class, version, workflow_digest, execution_policy_ref,
            execution_policy_digest, gate_policy_ref, gate_policy_digest,
            evidence_policy_ref, evidence_policy_digest
        FROM workflow_runs AS run
        WHERE run.tenant_id = %s AND run.ticket_id = %s
          AND run.episode_number = (
              SELECT current_episode FROM tickets
              WHERE tenant_id = %s AND ticket_id = %s
          )
        FOR UPDATE
        """,
        (actor.tenant_id, ticket_id, actor.tenant_id, ticket_id),
    ).fetchone()


def _refusal(
    evaluator: Workflow,
    proof_gate: ProofGate,
    actor: WorkflowActor,
    command: ResolveClose,
    run: dict[str, object] | None,
    connection: psycopg.Connection[dict[str, object]],
) -> RecordProblem | None:
    current_version = int(cast(int, run["version"])) if run is not None else 0
    if run is None or command.expected_version != current_version:
        return _problem(
            command,
            "version-conflict",
            409,
            "Workflow version conflict",
            current_version=current_version,
        )
    stored_ref = f"{run['workflow_key']}@{run['workflow_revision']}"
    if command.workflow_ref != stored_ref:
        return _problem(
            command,
            "workflow-not-terminal",
            409,
            "Workflow terminal state required",
            current_version=current_version,
        )
    if not _pins_match(evaluator, stored_ref, run):
        return _problem(
            command,
            "workflow-pin-mismatch",
            409,
            "Persisted Workflow pins do not match the composed catalog",
            current_version=current_version,
        )
    if not evaluator.is_terminal(stored_ref, str(run["current_stage"])):
        return _problem(
            command,
            "workflow-not-terminal",
            409,
            "Workflow terminal state required",
            current_version=current_version,
        )
    if not proof_gate.is_current(connection, actor.tenant_id, command.ticket_id):
        return _problem(
            command,
            "proof-incomplete",
            409,
            "Current proof is incomplete",
            current_version=current_version,
        )
    return None


def _pins_match(evaluator: Workflow, workflow_ref: str, run: dict[str, object]) -> bool:
    def digest(value: object) -> str:
        return f"sha256:{bytes(cast(bytes, value)).hex()}"

    return evaluator.pins_match(
        workflow_ref,
        digest(run["workflow_digest"]),
        (
            (str(run["execution_policy_ref"]), digest(run["execution_policy_digest"])),
            (str(run["gate_policy_ref"]), digest(run["gate_policy_digest"])),
            (str(run["evidence_policy_ref"]), digest(run["evidence_policy_digest"])),
        ),
    )


def _insert_lifecycle(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    command: ResolveClose,
    *,
    now: datetime,
) -> None:
    episode_row = cast(
        dict[str, object],
        connection.execute(
            "SELECT current_episode FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
            (actor.tenant_id, command.ticket_id),
        ).fetchone(),
    )
    episode = int(cast(int, episode_row["current_episode"]))
    sequence_row = cast(
        dict[str, object],
        connection.execute(
            """
            SELECT COALESCE(max(fact_sequence), 0) AS value FROM lifecycle_facts
            WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s
            """,
            (actor.tenant_id, command.ticket_id, episode),
        ).fetchone(),
    )
    first_sequence = int(cast(int, sequence_row["value"])) + 1
    connection.cursor().executemany(
        """
        INSERT INTO lifecycle_facts (
            lifecycle_fact_id, ticket_id, tenant_id, fact_sequence, state,
            actor_principal_id, client_command_id, recorded_at, episode_number, reason
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            (
                _uuid7(now),
                command.ticket_id,
                actor.tenant_id,
                sequence,
                state,
                actor.principal_id,
                command.client_command_id,
                now,
                episode,
                "proof-gated terminal close",
            )
            for sequence, state in (
                (first_sequence, "resolved"),
                (first_sequence + 1, "closed"),
            )
        ),
    )
    connection.execute(
        """
        UPDATE lifecycle_episodes SET state = 'closed', closed_at = %s
        WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s
        """,
        (now, actor.tenant_id, command.ticket_id, episode),
    )


def _closed_receipt(run: dict[str, object], command: ResolveClose) -> WorkflowReceipt:
    return WorkflowReceipt(
        command_id=command.client_command_id,
        event_ids=(),
        workflow_run_id=cast(UUID, run["workflow_run_id"]),
        ticket_id=command.ticket_id,
        workflow_ref=command.workflow_ref,
        stage=str(run["current_stage"]),
        activity_class=ActivityClass(str(run["activity_class"])),
        version=int(cast(int, run["version"])),
        lifecycle_facts=("resolved", "closed"),
    )


def _receipt(payload: dict[str, object]) -> WorkflowReceipt:
    return WorkflowReceipt(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        workflow_run_id=UUID(str(payload["workflow_run_id"])),
        ticket_id=UUID(str(payload["ticket_id"])),
        workflow_ref=str(payload["workflow_ref"]),
        stage=str(payload["stage"]),
        activity_class=ActivityClass(str(payload["activity_class"])),
        version=int(cast(int, payload["version"])),
        lifecycle_facts=tuple(str(item) for item in cast(list[object], payload["lifecycle_facts"])),
    )


def _problem(
    command: ResolveClose,
    code: str,
    status: int,
    title: str,
    *,
    current_version: int | None = None,
) -> RecordProblem:
    return RecordProblem(
        code,
        title,
        status,
        title,
        command.client_command_id,
        current_version=current_version,
    )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
