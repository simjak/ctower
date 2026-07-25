"""Workflow-owned atomic Postgres persistence."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

import psycopg

from ctower_kernel.record import RecordProblem
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.workflow import (
    ActivityClass,
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


class WorkReadinessGate(Protocol):
    """Admission/blocker query injected without a Workflow-to-Work import."""

    def unmet_facts(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> tuple[str, ...]: ...


def advance_workflow(
    dsn: str,
    evaluator: Workflow,
    proof_gate: ProofGate,
    readiness_gate: WorkReadinessGate,
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkflowReceipt | RecordProblem:
    """Reserve the command key before evaluating one graph edge."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        reserved = _reserve_workflow_outcome(
            transaction,
            actor,
            mutation,
            request_digest=request_digest,
            now=now,
        )
        if reserved is not None:
            return reserved
        if not _lock_open_ticket(connection, actor, mutation.ticket_id):
            return _refuse(
                transaction,
                actor,
                mutation,
                request_digest,
                _problem(mutation, "tenant-scope-denied", 404, "Open ticket not found"),
                now,
            )
        run = _lock_run(connection, actor, mutation.ticket_id)
        refusal = _transition_refusal(evaluator, actor, mutation, run)
        if refusal is not None:
            return _refuse(transaction, actor, mutation, request_digest, refusal, now)
        decision, unmet_facts = _evaluate_transition(
            connection, evaluator, proof_gate, readiness_gate, actor, mutation, run
        )
        if not decision.accepted:
            return _refuse(
                transaction,
                actor,
                mutation,
                request_digest,
                _problem(
                    mutation,
                    f"workflow-{decision.reason}",
                    409,
                    "Workflow transition refused",
                    current_version=_run_version(run),
                    unmet_facts=unmet_facts,
                ),
                now,
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


def _reserve_workflow_outcome(
    transaction: RecordTransaction,
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    *,
    request_digest: bytes,
    now: datetime,
) -> WorkflowReceipt | RecordProblem | None:
    existing = transaction.reserve(actor.principal_id, mutation.client_command_id, request_digest)
    if isinstance(existing, RecordProblem):
        return existing
    if existing is not None:
        return _receipt_from_payload(existing)
    return transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        mutation.client_command_id,
        request_digest,
        (("ticket", mutation.ticket_id),),
        now=now,
    )


def _evaluate_transition(
    connection: psycopg.Connection[dict[str, object]],
    evaluator: Workflow,
    proof_gate: ProofGate,
    readiness_gate: WorkReadinessGate,
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    run: dict[str, object] | None,
) -> tuple[WorkflowDecision, tuple[str, ...]]:
    predicates, unmet_facts = _satisfied_predicates(
        connection, proof_gate, readiness_gate, actor.tenant_id, mutation.ticket_id
    )
    decision = evaluator.evaluate(
        WorkflowContextSnapshot(
            workflow_ref=mutation.workflow_ref,
            current_stage=mutation.source_stage,
            satisfied_predicates=predicates,
            run_started=run is not None,
            tenant_id=actor.tenant_id,
            workflow_digest=_stored_digest(run, "workflow_digest"),
        ),
        WorkflowCommand(mutation.destination_stage),
    )
    return decision, unmet_facts


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
    if run is None:
        raise RuntimeError("accepted Workflow transition lacks an explicit run")
    run_id = cast(UUID, run["workflow_run_id"])
    version = _run_version(run) + 1
    activity = cast(ActivityClass, decision.activity_class)
    _persist_transition(
        connection,
        actor,
        mutation,
        run_id=run_id,
        version=version,
        activity=activity,
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


def _transition_refusal(
    evaluator: Workflow,
    actor: WorkflowActor,
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
        return _problem(
            mutation,
            "workflow-run-not-started",
            409,
            "Workflow run must be explicitly started",
            current_version=0,
        )
    stored_ref = f"{run['workflow_key']}@{run['workflow_revision']}"
    if mutation.workflow_ref != stored_ref or mutation.source_stage != run["current_stage"]:
        return _problem(
            mutation,
            "workflow-state-conflict",
            409,
            "Workflow state conflict",
            current_version=current_version,
        )
    if not _pins_match(evaluator, actor.tenant_id, stored_ref, run):
        return _problem(
            mutation,
            "workflow-pin-mismatch",
            409,
            "Persisted Workflow pins do not match the composed catalog",
            current_version=current_version,
        )
    if evaluator.is_terminal(
        mutation.workflow_ref,
        mutation.source_stage,
        tenant_id=actor.tenant_id,
        workflow_digest=_stored_digest(run, "workflow_digest"),
    ):
        return _problem(
            mutation,
            "workflow-terminal",
            409,
            "Workflow is already terminal",
            current_version=current_version,
        )
    return None


def _refuse(
    transaction: RecordTransaction,
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        mutation.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _pins_match(
    evaluator: Workflow,
    tenant_id: UUID,
    workflow_ref: str,
    run: dict[str, object],
) -> bool:
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
        tenant_id=tenant_id,
    )


def _stored_digest(run: dict[str, object] | None, key: str) -> str | None:
    if run is None:
        return None
    return "sha256:" + bytes(cast(bytes, run[key])).hex()


def _satisfied_predicates(
    connection: psycopg.Connection[dict[str, object]],
    proof_gate: ProofGate,
    readiness_gate: WorkReadinessGate,
    tenant_id: UUID,
    ticket_id: UUID,
) -> tuple[frozenset[str], tuple[str, ...]]:
    predicates: set[str] = set()
    unmet_facts = readiness_gate.unmet_facts(connection, tenant_id, ticket_id)
    if not unmet_facts:
        predicates.add("entry.ready@1")
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
    return frozenset(predicates), unmet_facts


def _persist_transition(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    mutation: WorkflowMutation,
    *,
    run_id: UUID,
    version: int,
    activity: ActivityClass,
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
) -> None:
    if version <= 1:
        raise RuntimeError("Workflow transitions must follow an explicit start")
    connection.execute(
        """
        UPDATE workflow_runs SET current_stage = %s, activity_class = %s, version = %s
        WHERE workflow_run_id = %s AND tenant_id = %s
        """,
        (
            mutation.destination_stage,
            activity.value,
            version,
            run_id,
            actor.tenant_id,
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


def _problem(
    request: WorkflowMutation,
    code: str,
    status: int,
    title: str,
    *,
    current_version: int | None = None,
    unmet_facts: tuple[str, ...] = (),
) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=request.client_command_id,
        current_version=current_version,
        unmet_facts=unmet_facts,
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
