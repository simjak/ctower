"""Adversarial public-interface Workflow and Proof integrity evidence."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from support.server import running_api
from support.tenant_fixture import TenantFixture

from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    EvidenceRequest,
    FreezeCriteriaRequest,
    Priority,
    ProofCriterion,
    SourceReference,
    TicketCreateRequest,
    VerdictRequest,
    WorkflowTransitionRequest,
)
from ctower_client import (
    Problem as HttpProblem,
)
from ctower_client import (
    VerdictDecision as HttpVerdictDecision,
)
from ctower_kernel.proof import (
    Criterion,
    FreezeCriteria,
    Proof,
    ProofActor,
    ProofMutation,
    ProofReceipt,
    RecordEvidence,
    RecordVerdict,
    VerdictDecision,
)
from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    RecordProblem,
    TicketCommand,
)
from ctower_kernel.record import (
    SourceReference as RecordSourceReference,
)
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from ctower_kernel.workflow import (
    ActivityClass,
    Stage,
    Transition,
    Workflow,
    WorkflowActor,
    WorkflowGraph,
    WorkflowMutation,
    WorkflowReceipt,
)
from ctower_kernel.workflow.postgres import PostgresWorkflow

__all__: tuple[str, ...] = ()
WORKFLOW_REF = "ctower.trust-spine-four-stage@1"
CANDIDATE_DIGEST = "sha256:" + "a" * 64
EARLIER = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 20, 13, 0, tzinfo=UTC)
ROOT = Path(__file__).parents[3]
VERIFY_VERSION = 2
CLOSE_VERSION = 3
FIRST_VERDICT_SEQUENCE = 3
SECOND_VERDICT_SEQUENCE = 4


@pytest.mark.parametrize(
    (
        "first_decision",
        "second_decision",
        "first_time",
        "second_time",
        "first_verdict_id",
        "second_verdict_id",
    ),
    (
        (
            VerdictDecision.PASSING,
            VerdictDecision.FAILING,
            LATER,
            EARLIER,
            UUID("40000000-0000-4000-8000-000000000001"),
            UUID("40000000-0000-4000-8000-000000000002"),
        ),
        (
            VerdictDecision.PASSING,
            VerdictDecision.FAILING,
            EARLIER,
            EARLIER,
            UUID("ffffffff-ffff-4fff-bfff-ffffffffffff"),
            UUID("00000000-0000-4000-8000-000000000001"),
        ),
        (
            VerdictDecision.FAILING,
            VerdictDecision.PASSING,
            LATER,
            EARLIER,
            UUID("40000000-0000-4000-8000-000000000003"),
            UUID("40000000-0000-4000-8000-000000000004"),
        ),
    ),
)
def test_verdict_commit_sequence_controls_current_proof(
    tenant: TenantFixture,
    first_decision: VerdictDecision,
    second_decision: VerdictDecision,
    first_time: datetime,
    second_time: datetime,
    first_verdict_id: UUID,
    second_verdict_id: UUID,
) -> None:
    expected_current = second_decision is VerdictDecision.PASSING
    proof_store, workflow, ticket_id = _prepare_verification_stage(tenant)
    reviewer = ProofActor(tenant.operator_id, tenant.tenant_id, "operator")
    first, second = _record_verdict_pair(
        proof_store,
        reviewer,
        ticket_id,
        first=(first_verdict_id, first_decision, first_time),
        second=(second_verdict_id, second_decision, second_time),
    )
    movement = _attempt_close(workflow, tenant, ticket_id)

    assert first.satisfied is (first_decision is VerdictDecision.PASSING)
    assert second.satisfied is expected_current
    _assert_close_outcome(movement, expected_current=expected_current)
    assert _verdict_facts(tenant.database.admin_dsn, ticket_id) == (
        (FIRST_VERDICT_SEQUENCE, first_verdict_id, first_time),
        (SECOND_VERDICT_SEQUENCE, second_verdict_id, second_time),
    )
    assert _workflow_version(tenant.database.admin_dsn, ticket_id) == (
        CLOSE_VERSION if expected_current else VERIFY_VERSION
    )


def _assert_close_outcome(
    movement: WorkflowReceipt | RecordProblem, *, expected_current: bool
) -> None:
    if expected_current:
        assert isinstance(movement, WorkflowReceipt)
        assert movement.stage == "close"
        assert movement.version == CLOSE_VERSION
        return
    assert isinstance(movement, RecordProblem)
    assert movement.code == "workflow-predicate-unsatisfied"
    assert movement.current_version == VERIFY_VERSION


def _record_verdict_pair(
    store: PostgresProof,
    reviewer: ProofActor,
    ticket_id: UUID,
    *,
    first: tuple[UUID, VerdictDecision, datetime],
    second: tuple[UUID, VerdictDecision, datetime],
) -> tuple[ProofReceipt, ProofReceipt]:
    first_receipt = _record_verdict_at(
        store,
        reviewer,
        ticket_id,
        expected_version=2,
        verdict_id=first[0],
        decision=first[1],
        recorded_at=first[2],
    )
    second_receipt = _record_verdict_at(
        store,
        reviewer,
        ticket_id,
        expected_version=3,
        verdict_id=second[0],
        decision=second[1],
        recorded_at=second[2],
    )
    return first_receipt, second_receipt


def _attempt_close(
    workflow: Workflow, tenant: TenantFixture, ticket_id: UUID
) -> WorkflowReceipt | RecordProblem:
    return workflow.advance(
        WorkflowActor(tenant.commander_id, tenant.tenant_id),
        WorkflowMutation(
            uuid4(),
            ticket_id,
            "fixture.verdict-order@1",
            VERIFY_VERSION,
            "verify",
            "close",
        ),
        telemetry=_telemetry(),
    )


def test_corrective_migration_backfills_committed_verdict_sequences(
    tenant: TenantFixture,
) -> None:
    proof_store, _, ticket_id = _prepare_verification_stage(tenant)
    reviewer = ProofActor(tenant.operator_id, tenant.tenant_id, "operator")
    first_id = UUID("40000000-0000-4000-8000-000000000005")
    second_id = UUID("40000000-0000-4000-8000-000000000006")
    _record_verdict_at(
        proof_store,
        reviewer,
        ticket_id,
        expected_version=2,
        verdict_id=first_id,
        decision=VerdictDecision.PASSING,
        recorded_at=LATER,
    )
    _record_verdict_at(
        proof_store,
        reviewer,
        ticket_id,
        expected_version=3,
        verdict_id=second_id,
        decision=VerdictDecision.FAILING,
        recorded_at=EARLIER,
    )

    migration = (
        ROOT / "packages/ctower-kernel/migrations/0005_proof_verdict_sequence.sql"
    ).read_text(encoding="utf-8")
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute("ALTER TABLE proof_verdicts DROP COLUMN proof_sequence CASCADE")
        connection.execute(migration)

    assert _verdict_facts(tenant.database.admin_dsn, ticket_id) == (
        (FIRST_VERDICT_SEQUENCE, first_id, LATER),
        (SECOND_VERDICT_SEQUENCE, second_id, EARLIER),
    )


def test_fresh_run_refuses_a_later_declared_edge_without_mutation(
    tenant: TenantFixture,
) -> None:
    with running_api(tenant.database.runtime_dsn) as base_url:
        with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
            ticket_id = _create_ticket(commander, tenant)
            _record_current_evidence(commander, ticket_id)
        with CtowerClient(base_url, credential=tenant.operator_credential) as operator:
            _record_passing_verdict(operator, ticket_id)
        with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
            with pytest.raises(CtowerProblemError) as refused:
                commander.transition_workflow(
                    ticket_id,
                    WorkflowTransitionRequest(
                        expected_version=0,
                        workflow_ref=WORKFLOW_REF,
                        source_stage="verify",
                        destination_stage="close",
                    ),
                    command_id=uuid4(),
                )
            assert refused.value.problem.code == "workflow-initial-stage-required"
            assert cast(HttpProblem, refused.value.problem).current_version == 0
            assert _workflow_row_counts(tenant.database.admin_dsn, ticket_id) == (0, 0)

            first_movement = commander.transition_workflow(
                ticket_id,
                WorkflowTransitionRequest(
                    expected_version=0,
                    workflow_ref=WORKFLOW_REF,
                    source_stage="capture",
                    destination_stage="frame",
                ),
                command_id=uuid4(),
            )

    assert first_movement.stage == "frame"
    assert first_movement.version == 1


def _create_ticket(client: CtowerClient, tenant: TenantFixture) -> UUID:
    return client.create_ticket(
        TicketCreateRequest(
            initial_custodian_id=tenant.commander_id,
            priority=Priority.P1,
            source=SourceReference(kind="test", ref=f"test:workflow-integrity:{uuid4()}"),
            title="Workflow integrity",
        ),
        command_id=uuid4(),
    ).ticket.ticket_id


def _record_current_evidence(client: CtowerClient, ticket_id: UUID) -> None:
    content = "current workflow-integrity evidence"
    client.freeze_proof_criteria(
        ticket_id,
        FreezeCriteriaRequest(
            expected_version=0,
            candidate_digest=CANDIDATE_DIGEST,
            criteria=(
                ProofCriterion(
                    key="artifact-current",
                    description="The candidate artifact is current.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
        command_id=uuid4(),
    )
    client.record_proof_evidence(
        ticket_id,
        EvidenceRequest(
            expected_version=1,
            evidence_id=uuid4(),
            criterion_key="artifact-current",
            candidate_digest=CANDIDATE_DIGEST,
            artifact_digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
            content=content,
        ),
        command_id=uuid4(),
    )


def _record_passing_verdict(client: CtowerClient, ticket_id: UUID) -> None:
    client.record_proof_verdict(
        ticket_id,
        VerdictRequest(
            expected_version=2,
            verdict_id=uuid4(),
            criterion_key="artifact-current",
            candidate_digest=CANDIDATE_DIGEST,
            decision=HttpVerdictDecision.PASS,
        ),
        command_id=uuid4(),
    )


def _prepare_verification_stage(
    tenant: TenantFixture,
) -> tuple[PostgresProof, Workflow, UUID]:
    record = PostgresRecord(tenant.database.runtime_dsn)
    ticket = Work(record).create_ticket(
        Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER),
        TicketCommand(
            uuid4(),
            tenant.commander_id,
            "P1",
            RecordSourceReference("test", f"test:verdict-order:{uuid4()}"),
            "Verdict order integrity",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(ticket, RecordProblem)
    ticket_id = ticket.ticket.ticket_id
    proof_store = PostgresProof(tenant.database.runtime_dsn)
    workflow_store = PostgresWorkflow(tenant.database.runtime_dsn, proof_gate=proof_store)
    workflow = Workflow((_verdict_workflow_graph(),), writer=workflow_store)
    actor = WorkflowActor(tenant.commander_id, tenant.tenant_id)
    first = workflow.advance(
        actor,
        WorkflowMutation(uuid4(), ticket_id, "fixture.verdict-order@1", 0, "capture", "frame"),
        telemetry=_telemetry(),
    )
    assert isinstance(first, WorkflowReceipt)
    _freeze_and_record_evidence(proof_store, tenant, ticket_id)
    verification = workflow.advance(
        actor,
        WorkflowMutation(uuid4(), ticket_id, "fixture.verdict-order@1", 1, "frame", "verify"),
        telemetry=_telemetry(),
    )
    assert isinstance(verification, WorkflowReceipt)
    return proof_store, workflow, ticket_id


def _verdict_workflow_graph() -> WorkflowGraph:
    return WorkflowGraph(
        key="fixture.verdict-order",
        revision=1,
        initial_stage="capture",
        stages=(
            Stage("capture", ActivityClass.WORK),
            Stage("frame", ActivityClass.WORK),
            Stage("verify", ActivityClass.VERIFICATION),
            Stage("close", ActivityClass.WORK),
        ),
        transitions=(
            Transition("capture", "frame", "entry.ready@1"),
            Transition("frame", "verify", "criteria.frozen@1"),
            Transition("verify", "close", "proof.current@1"),
        ),
    )


def _freeze_and_record_evidence(
    store: PostgresProof, tenant: TenantFixture, ticket_id: UUID
) -> None:
    proof = Proof(writer=store)
    author = ProofActor(tenant.commander_id, tenant.tenant_id, "commander")
    frozen = proof.execute(
        author,
        ProofMutation(
            uuid4(),
            ticket_id,
            0,
            FreezeCriteria(
                CANDIDATE_DIGEST,
                tenant.commander_id,
                (
                    Criterion(
                        key="artifact-current",
                        description="The candidate artifact is current.",
                        candidate_dependent=True,
                        requires_verdict=True,
                    ),
                ),
            ),
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(frozen, ProofReceipt)
    content = b"verdict order evidence"
    evidence = proof.execute(
        author,
        ProofMutation(
            uuid4(),
            ticket_id,
            1,
            RecordEvidence(
                uuid4(),
                "artifact-current",
                CANDIDATE_DIGEST,
                "sha256:" + hashlib.sha256(content).hexdigest(),
                content,
            ),
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(evidence, ProofReceipt)


def _record_verdict_at(
    store: PostgresProof,
    reviewer: ProofActor,
    ticket_id: UUID,
    *,
    expected_version: int,
    verdict_id: UUID,
    decision: VerdictDecision,
    recorded_at: datetime,
) -> ProofReceipt:
    outcome = Proof(writer=store, clock=lambda: recorded_at).execute(
        reviewer,
        ProofMutation(
            uuid4(),
            ticket_id,
            expected_version,
            RecordVerdict(verdict_id, "artifact-current", CANDIDATE_DIGEST, decision),
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(outcome, ProofReceipt)
    return outcome


def _workflow_version(dsn: str, ticket_id: UUID) -> int:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            "SELECT version FROM workflow_runs WHERE ticket_id = %s",
            (ticket_id,),
        ).fetchone()
    assert row is not None
    return int(row["version"])


def _verdict_facts(dsn: str, ticket_id: UUID) -> tuple[tuple[int, UUID, datetime], ...]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT verdict.proof_sequence, verdict.verdict_id, verdict.recorded_at
            FROM proof_verdicts AS verdict
            JOIN proof_bundles AS bundle USING (proof_id)
            WHERE bundle.ticket_id = %s
            ORDER BY verdict.proof_sequence
            """,
            (ticket_id,),
        ).fetchall()
    return tuple(
        (
            int(row["proof_sequence"]),
            UUID(str(row["verdict_id"])),
            row["recorded_at"],
        )
        for row in rows
        if isinstance(row["recorded_at"], datetime)
    )


def _telemetry() -> TelemetryContext:
    correlation = uuid4()
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="1" * 32,
        span_id="2" * 16,
        trace_flags=1,
        correlation_id=str(correlation),
        causation_id=str(correlation),
        tenant_id="",
        actor_id="",
        command_id="",
    )


def _workflow_row_counts(dsn: str, ticket_id: UUID) -> tuple[int, int]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM workflow_runs WHERE ticket_id = %s) AS runs,
                (SELECT count(*) FROM workflow_transition_facts AS f
                    JOIN workflow_runs AS r USING (workflow_run_id)
                    WHERE r.ticket_id = %s) AS transitions
            """,
            (ticket_id, ticket_id),
        ).fetchone()
    assert row is not None
    return int(row["runs"]), int(row["transitions"])
