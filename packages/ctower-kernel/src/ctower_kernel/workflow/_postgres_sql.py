"""Workflow-owned atomic Postgres persistence."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Protocol, cast
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
    WorkflowCommand,
    WorkflowContextSnapshot,
    WorkflowDecision,
    WorkflowMutation,
    WorkflowReceipt,
)
from ctower_kernel.workflow._event_sql import append_change as _append_change

__all__: tuple[str, ...] = ()


class ProofGate(Protocol):
    """Current-proof query injected by composition without a Workflow-to-Proof import."""

    def is_current(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> bool: ...


def advance_workflow(
    dsn: str,
    evaluator: Workflow,
    proof_gate: ProofGate,
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkflowReceipt | RecordProblem:
    """Reserve the command key before evaluating one graph edge."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id, mutation.client_command_id, request_digest
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _receipt_from_payload(existing)
        if not _lock_open_ticket(connection, actor, mutation.ticket_id):
            return _problem(mutation, "tenant-scope-denied", 404, "Open ticket not found")
        run = _lock_run(connection, actor, mutation.ticket_id)
        refusal = _transition_refusal(evaluator, mutation, run)
        if refusal is not None:
            return refusal
        decision = _evaluate_transition(connection, evaluator, proof_gate, actor, mutation, run)
        if not decision.accepted:
            return _problem(
                mutation,
                f"workflow-{decision.reason}",
                409,
                "Workflow transition refused",
                current_version=_run_version(run),
            )
        return _commit_transition(
            connection,
            actor,
            mutation,
            run,
            decision,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _evaluate_transition(
    connection: psycopg.Connection[dict[str, object]],
    evaluator: Workflow,
    proof_gate: ProofGate,
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    run: dict[str, object] | None,
) -> WorkflowDecision:
    return evaluator.evaluate(
        WorkflowContextSnapshot(
            workflow_ref=mutation.workflow_ref,
            current_stage=mutation.source_stage,
            satisfied_predicates=_satisfied_predicates(
                connection, proof_gate, actor.tenant_id, mutation.ticket_id
            ),
            run_started=run is not None,
        ),
        WorkflowCommand(mutation.destination_stage),
    )


def _commit_transition(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    run: dict[str, object] | None,
    decision: WorkflowDecision,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkflowReceipt:
    run_id = cast(UUID, run["workflow_run_id"]) if run is not None else _uuid7(now)
    version = _run_version(run) + 1
    activity = cast(ActivityClass, decision.activity_class)
    _persist_transition(
        connection,
        actor,
        mutation,
        run_id=run_id,
        version=version,
        activity=activity,
        initial_stage=cast(str, decision.initial_stage),
        predicate_ref=cast(str, decision.predicate_ref),
        now=now,
    )
    receipt = WorkflowReceipt(
        command_id=mutation.client_command_id,
        event_ids=(),
        workflow_run_id=run_id,
        ticket_id=mutation.ticket_id,
        workflow_ref=mutation.workflow_ref,
        stage=mutation.destination_stage,
        activity_class=activity,
        version=version,
    )
    return _append_change(
        connection,
        actor,
        mutation.client_command_id,
        receipt,
        operation="transition",
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )


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
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id, command.client_command_id, request_digest
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _receipt_from_payload(existing)
        if not _lock_open_ticket(connection, actor, command.ticket_id):
            return _problem(command, "tenant-scope-denied", 404, "Open ticket not found")
        run = _lock_run(connection, actor, command.ticket_id)
        refusal = _close_refusal(evaluator, proof_gate, actor, command, run, connection)
        if refusal is not None:
            return refusal
        _insert_lifecycle(connection, actor, command, now=now)
        receipt = _closed_receipt(cast(dict[str, object], run), command)
        receipt = _append_change(
            connection,
            actor,
            command.client_command_id,
            receipt,
            operation="resolve_close",
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
    return receipt


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


def _lock_open_ticket(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    ticket_id: UUID,
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM tickets AS t
        WHERE t.tenant_id = %s AND t.ticket_id = %s
          AND NOT EXISTS (
              SELECT 1 FROM lifecycle_facts AS f
              WHERE f.tenant_id = t.tenant_id AND f.ticket_id = t.ticket_id
                AND f.state = 'closed'
          )
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
            activity_class, version
        FROM workflow_runs WHERE tenant_id = %s AND ticket_id = %s FOR UPDATE
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()


def _transition_refusal(
    evaluator: Workflow,
    mutation: WorkflowMutation,
    run: dict[str, object] | None,
) -> RecordProblem | None:
    current_version = _run_version(run)
    if mutation.expected_version != current_version:
        return _problem(
            mutation,
            "version-conflict",
            409,
            "Workflow version conflict",
            current_version=current_version,
        )
    if run is None:
        return None
    stored_ref = f"{run['workflow_key']}@{run['workflow_revision']}"
    if mutation.workflow_ref != stored_ref or mutation.source_stage != run["current_stage"]:
        return _problem(
            mutation,
            "workflow-state-conflict",
            409,
            "Workflow state conflict",
            current_version=current_version,
        )
    if evaluator.is_terminal(mutation.workflow_ref, mutation.source_stage):
        return _problem(
            mutation,
            "workflow-terminal",
            409,
            "Workflow is already terminal",
            current_version=current_version,
        )
    return None


def _close_refusal(
    evaluator: Workflow,
    proof_gate: ProofGate,
    actor: WorkflowActor,
    command: ResolveClose,
    run: dict[str, object] | None,
    connection: psycopg.Connection[dict[str, object]],
) -> RecordProblem | None:
    current_version = _run_version(run)
    if run is None or command.expected_version != current_version:
        return _problem(
            command,
            "version-conflict",
            409,
            "Workflow version conflict",
            current_version=current_version,
        )
    stored_ref = f"{run['workflow_key']}@{run['workflow_revision']}"
    stage = str(run["current_stage"])
    if command.workflow_ref != stored_ref or not evaluator.is_terminal(stored_ref, stage):
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


def _satisfied_predicates(
    connection: psycopg.Connection[dict[str, object]],
    proof_gate: ProofGate,
    tenant_id: UUID,
    ticket_id: UUID,
) -> frozenset[str]:
    predicates = {"entry.ready@1"}
    criteria = connection.execute(
        """
        SELECT 1 FROM proof_bundles AS b
        JOIN proof_criteria AS c ON c.proof_id = b.proof_id AND c.tenant_id = b.tenant_id
        WHERE b.tenant_id = %s AND b.ticket_id = %s LIMIT 1
        """,
        (tenant_id, ticket_id),
    ).fetchone()
    if criteria is not None:
        predicates.add("criteria.frozen@1")
    if proof_gate.is_current(connection, tenant_id, ticket_id):
        predicates.add("proof.current@1")
    return frozenset(predicates)


def _persist_transition(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    *,
    run_id: UUID,
    version: int,
    activity: ActivityClass,
    initial_stage: str,
    predicate_ref: str,
    now: datetime,
) -> None:
    _persist_run_head(
        connection,
        actor,
        mutation,
        run_id=run_id,
        version=version,
        activity=activity,
        initial_stage=initial_stage,
        now=now,
    )
    connection.execute(
        """
        INSERT INTO workflow_transition_facts (
            transition_id, workflow_run_id, tenant_id, fact_sequence, source_stage,
            destination_stage, predicate_ref, activity_class, actor_principal_id,
            client_command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            _uuid7(now),
            run_id,
            actor.tenant_id,
            version,
            mutation.source_stage,
            mutation.destination_stage,
            predicate_ref,
            activity.value,
            actor.principal_id,
            mutation.client_command_id,
            now,
        ),
    )


def _persist_run_head(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    *,
    run_id: UUID,
    version: int,
    activity: ActivityClass,
    initial_stage: str,
    now: datetime,
) -> None:
    if version != 1:
        connection.execute(
            """
            UPDATE workflow_runs SET current_stage = %s, activity_class = %s, version = %s
            WHERE workflow_run_id = %s AND tenant_id = %s
            """,
            (mutation.destination_stage, activity.value, version, run_id, actor.tenant_id),
        )
        return
    key, revision = mutation.workflow_ref.rsplit("@", 1)
    connection.execute(
        """
        INSERT INTO workflow_runs (
            workflow_run_id, ticket_id, tenant_id, workflow_key, workflow_revision,
            initial_stage, current_stage, activity_class, version, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
        """,
        (
            run_id,
            mutation.ticket_id,
            actor.tenant_id,
            key,
            int(revision),
            initial_stage,
            mutation.destination_stage,
            activity.value,
            now,
        ),
    )


def _insert_lifecycle(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    command: ResolveClose,
    *,
    now: datetime,
) -> None:
    connection.cursor().executemany(
        """
        INSERT INTO lifecycle_facts (
            lifecycle_fact_id, ticket_id, tenant_id, fact_sequence, state,
            actor_principal_id, client_command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
            )
            for sequence, state in ((1, "resolved"), (2, "closed"))
        ),
    )


def _receipt_from_payload(payload: dict[str, object]) -> WorkflowReceipt:
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


def _run_version(run: dict[str, object] | None) -> int:
    return int(cast(int, run["version"])) if run is not None else 0


type _WorkflowRequest = WorkflowMutation | ResolveClose


def _problem(
    request: _WorkflowRequest,
    code: str,
    status: int,
    title: str,
    *,
    current_version: int | None = None,
) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=request.client_command_id,
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
