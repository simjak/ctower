"""Canonical four-stage Proof-gated Workflow acceptance evidence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from support.server import running_api, start_and_admit
from support.tenant_fixture import TenantFixture

from ctower_client import (
    CtowerClient,
    CtowerProblemError,
    EvidenceRequest,
    FreezeCriteriaRequest,
    Priority,
    ProofCriterion,
    ResolveCloseRequest,
    TicketCreateRequest,
    VerdictRequest,
    WorkflowTransitionRequest,
)
from ctower_client import (
    ProofReceipt as HttpProofReceipt,
)
from ctower_client import (
    SourceReference as HttpSourceReference,
)
from ctower_client import (
    VerdictDecision as HttpVerdictDecision,
)
from ctower_client import (
    WorkflowReceipt as HttpWorkflowReceipt,
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
    SourceReference,
    TicketCommand,
)
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work
from ctower_kernel.workflow import (
    ActivityClass,
    ResolveClose,
    Stage,
    Transition,
    Workflow,
    WorkflowActor,
    WorkflowGraph,
    WorkflowMutation,
    WorkflowReceipt,
    WorkflowStart,
)
from ctower_kernel.workflow.postgres import PostgresWorkflow

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _PreparedTrace:
    ticket_id: UUID
    frame: HttpWorkflowReceipt
    frozen: HttpProofReceipt
    verification: HttpWorkflowReceipt
    corrupt_code: str
    evidence: HttpProofReceipt
    self_review_code: str


class _AlwaysReady:
    def unmet_facts(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> tuple[str, ...]:
        del connection, tenant_id, ticket_id
        return ()


def test_generated_client_drives_the_four_stage_fixture(tenant: TenantFixture) -> None:
    candidate_digest = "sha256:" + "c" * 64
    content = "four-stage evidence"
    artifact_digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    with running_api(tenant.database.runtime_dsn) as base_url:
        with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
            prepared = _prepare_public_trace(
                commander, tenant, candidate_digest, artifact_digest, content
            )
        with CtowerClient(base_url, credential=tenant.operator_credential) as operator:
            verdict = operator.record_proof_verdict(
                prepared.ticket_id,
                VerdictRequest(
                    expected_version=2,
                    verdict_id=uuid4(),
                    criterion_key="artifact-current",
                    candidate_digest=candidate_digest,
                    decision=HttpVerdictDecision.PASS,
                ),
                command_id=uuid4(),
            )
        with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
            terminal, closed = _close_public_trace(commander, prepared.ticket_id)

    assert prepared.frame.stage == "frame"
    assert prepared.frozen.version == 1
    assert prepared.verification.activity_class == "verification"
    assert prepared.corrupt_code == "proof-evidence-digest-mismatch"
    assert prepared.evidence.version == prepared.frozen.version + 1
    assert prepared.self_review_code == "proof-self-review-refused"
    assert verdict.satisfied is True
    assert terminal.stage == "close"
    assert closed.lifecycle_facts == ("resolved", "closed")


def _prepare_public_trace(
    commander: CtowerClient,
    tenant: TenantFixture,
    candidate_digest: str,
    artifact_digest: str,
    content: str,
) -> _PreparedTrace:
    ticket = commander.create_ticket(
        TicketCreateRequest(
            initial_custodian_id=tenant.commander_id,
            priority=Priority.P1,
            source=HttpSourceReference(kind="test", ref="test:four-stage"),
            title="Four-stage proof workflow",
        ),
        command_id=uuid4(),
    ).ticket
    start_and_admit(commander, ticket.ticket_id)
    frame, frozen, verification = _reach_verification(commander, ticket.ticket_id, candidate_digest)
    corrupt_code, evidence = _record_public_evidence(
        commander, ticket.ticket_id, candidate_digest, artifact_digest, content
    )
    self_review_code = _refuse_self_review(commander, ticket.ticket_id, candidate_digest)
    return _PreparedTrace(
        ticket.ticket_id,
        frame,
        frozen,
        verification,
        corrupt_code,
        evidence,
        self_review_code,
    )


def _reach_verification(
    commander: CtowerClient, ticket_id: UUID, candidate_digest: str
) -> tuple[HttpWorkflowReceipt, HttpProofReceipt, HttpWorkflowReceipt]:
    workflow_ref = "ctower.trust-spine-four-stage@1"
    frame = commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=1,
            workflow_ref=workflow_ref,
            source_stage="capture",
            destination_stage="frame",
        ),
        command_id=uuid4(),
    )
    frozen = commander.freeze_proof_criteria(
        ticket_id,
        FreezeCriteriaRequest(
            expected_version=0,
            candidate_digest=candidate_digest,
            criteria=(
                ProofCriterion(
                    key="artifact-current",
                    description="Current artifact.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
        command_id=uuid4(),
    )
    verification = commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=2,
            workflow_ref=workflow_ref,
            source_stage="frame",
            destination_stage="verify",
        ),
        command_id=uuid4(),
    )
    return frame, frozen, verification


def _record_public_evidence(
    commander: CtowerClient,
    ticket_id: UUID,
    candidate_digest: str,
    artifact_digest: str,
    content: str,
) -> tuple[str, HttpProofReceipt]:
    with pytest.raises(CtowerProblemError) as corrupt:
        commander.record_proof_evidence(
            ticket_id,
            EvidenceRequest(
                expected_version=1,
                evidence_id=uuid4(),
                criterion_key="artifact-current",
                candidate_digest=candidate_digest,
                artifact_digest=artifact_digest,
                content="corrupt",
            ),
            command_id=uuid4(),
        )
    evidence = commander.record_proof_evidence(
        ticket_id,
        EvidenceRequest(
            expected_version=1,
            evidence_id=uuid4(),
            criterion_key="artifact-current",
            candidate_digest=candidate_digest,
            artifact_digest=artifact_digest,
            content=content,
        ),
        command_id=uuid4(),
    )
    return corrupt.value.problem.code, evidence


def _refuse_self_review(commander: CtowerClient, ticket_id: UUID, candidate_digest: str) -> str:
    with pytest.raises(CtowerProblemError) as refused:
        commander.record_proof_verdict(
            ticket_id,
            VerdictRequest(
                expected_version=2,
                verdict_id=uuid4(),
                criterion_key="artifact-current",
                candidate_digest=candidate_digest,
                decision=HttpVerdictDecision.PASS,
            ),
            command_id=uuid4(),
        )
    return refused.value.problem.code


def _close_public_trace(
    commander: CtowerClient, ticket_id: UUID
) -> tuple[HttpWorkflowReceipt, HttpWorkflowReceipt]:
    workflow_ref = "ctower.trust-spine-four-stage@1"
    terminal = commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=3,
            workflow_ref=workflow_ref,
            source_stage="verify",
            destination_stage="close",
        ),
        command_id=uuid4(),
    )
    closed = commander.resolve_close_workflow(
        ticket_id,
        ResolveCloseRequest(expected_version=4, workflow_ref=workflow_ref),
        command_id=uuid4(),
    )
    return terminal, closed


def test_close_requires_current_proof_and_appends_resolved_then_closed_atomically(
    tenant: TenantFixture,
) -> None:
    proof_store, workflow, workflow_actor, ticket_id = _terminal_context(tenant)
    close_id = uuid4()
    close = ResolveClose(
        client_command_id=close_id,
        ticket_id=ticket_id,
        workflow_ref="fixture.atomic-close@1",
        expected_version=2,
    )

    refused = workflow.resolve_close(workflow_actor, close, telemetry=_telemetry())

    assert isinstance(refused, RecordProblem)
    assert refused.code == "proof-incomplete"
    _assert_lifecycle(tenant.database.admin_dsn, ticket_id, expected=())

    _complete_proof(proof_store, tenant, ticket_id)

    refused_replay = workflow.resolve_close(workflow_actor, close, telemetry=_telemetry())
    committed_close_id = uuid4()
    committed_close = ResolveClose(
        client_command_id=committed_close_id,
        ticket_id=ticket_id,
        workflow_ref="fixture.atomic-close@1",
        expected_version=2,
    )
    committed = workflow.resolve_close(workflow_actor, committed_close, telemetry=_telemetry())
    replay = workflow.resolve_close(workflow_actor, committed_close, telemetry=_telemetry())

    assert refused_replay == refused
    assert isinstance(committed, WorkflowReceipt)
    assert replay == committed
    assert committed.lifecycle_facts == ("resolved", "closed")
    _assert_lifecycle(
        tenant.database.admin_dsn,
        ticket_id,
        expected=(
            (1, "resolved", committed_close_id),
            (2, "closed", committed_close_id),
        ),
    )


def _terminal_context(
    tenant: TenantFixture,
) -> tuple[PostgresProof, Workflow, WorkflowActor, UUID]:
    proof_store = PostgresProof(tenant.database.runtime_dsn)
    workflow_store = PostgresWorkflow(
        tenant.database.runtime_dsn,
        proof_gate=proof_store,
        readiness_gate=_AlwaysReady(),
    )
    ticket_id = _create_ticket(tenant)
    graph = _terminal_graph()
    workflow = Workflow(
        (graph,),
        writer=workflow_store,
        policy_digests={
            "fixture.execution@1": "sha256:" + "1" * 64,
            "fixture.gates@1": "sha256:" + "2" * 64,
            "fixture.evidence@1": "sha256:" + "3" * 64,
        },
    )
    actor = WorkflowActor(tenant.commander_id, tenant.tenant_id)
    started = workflow.start(
        actor,
        WorkflowStart(
            uuid4(),
            ticket_id,
            graph.reference,
            graph.digest,
            "fixture.execution@1",
            "sha256:" + "1" * 64,
            "fixture.gates@1",
            "sha256:" + "2" * 64,
            "fixture.evidence@1",
            "sha256:" + "3" * 64,
        ),
        telemetry=_telemetry(),
    )
    moved = workflow.advance(
        actor,
        WorkflowMutation(
            client_command_id=uuid4(),
            ticket_id=ticket_id,
            workflow_ref="fixture.atomic-close@1",
            expected_version=1,
            source_stage="start",
            destination_stage="terminal",
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(started, WorkflowReceipt)
    assert isinstance(moved, WorkflowReceipt)
    return proof_store, workflow, actor, ticket_id


def _create_ticket(tenant: TenantFixture) -> UUID:
    commander = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    ticket = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        commander,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P1",
            source=SourceReference("test", "test:proof-close"),
            title="Proof-gated close",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(ticket, RecordProblem)
    return ticket.ticket.ticket_id


def _terminal_graph() -> WorkflowGraph:
    return WorkflowGraph(
        key="fixture.atomic-close",
        revision=1,
        initial_stage="start",
        stages=(
            Stage("start", ActivityClass.WORK),
            Stage("terminal", ActivityClass.WORK),
        ),
        transitions=(Transition("start", "terminal", "entry.ready@1"),),
        execution_policy_ref="fixture.execution@1",
        gate_policy_ref="fixture.gates@1",
    )


def _complete_proof(store: PostgresProof, tenant: TenantFixture, ticket_id: UUID) -> None:
    proof = Proof(writer=store)
    author = ProofActor(tenant.commander_id, tenant.tenant_id, "commander")
    reviewer = ProofActor(tenant.operator_id, tenant.tenant_id, "operator")
    candidate_digest = "sha256:" + "a" * 64
    _freeze_and_replay(proof, author, ticket_id, candidate_digest)
    content = b"current proof"
    evidence = proof.execute(
        author,
        ProofMutation(
            uuid4(),
            ticket_id,
            1,
            RecordEvidence(
                uuid4(),
                "current",
                candidate_digest,
                "sha256:" + hashlib.sha256(content).hexdigest(),
                content,
            ),
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(evidence, ProofReceipt)
    verdict = proof.execute(
        reviewer,
        ProofMutation(
            uuid4(),
            ticket_id,
            2,
            RecordVerdict(uuid4(), "current", candidate_digest, VerdictDecision.PASSING),
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(verdict, ProofReceipt)


def _freeze_and_replay(
    proof: Proof, author: ProofActor, ticket_id: UUID, candidate_digest: str
) -> None:
    command_id = uuid4()
    mutation = ProofMutation(
        command_id,
        ticket_id,
        0,
        FreezeCriteria(
            candidate_digest,
            author.principal_id,
            (
                Criterion(
                    key="current",
                    description="Evidence is current.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
    )
    frozen = proof.execute(author, mutation, telemetry=_telemetry())
    replay = proof.execute(author, mutation, telemetry=_telemetry())
    conflict = proof.execute(
        author,
        ProofMutation(
            command_id,
            ticket_id,
            0,
            FreezeCriteria(
                candidate_digest,
                author.principal_id,
                (
                    Criterion(
                        key="other",
                        description="Incompatible replay.",
                        candidate_dependent=True,
                        requires_verdict=True,
                    ),
                ),
            ),
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(frozen, ProofReceipt)
    assert replay == frozen
    assert isinstance(conflict, RecordProblem)
    assert conflict.code == "idempotency-conflict"


def _assert_lifecycle(
    dsn: str,
    ticket_id: UUID,
    *,
    expected: tuple[tuple[int, str, UUID], ...],
) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT fact_sequence, state, client_command_id
            FROM lifecycle_facts WHERE ticket_id = %s ORDER BY fact_sequence
            """,
            (ticket_id,),
        ).fetchall()
    assert (
        tuple(
            (int(row["fact_sequence"]), str(row["state"]), UUID(str(row["client_command_id"])))
            for row in rows
        )
        == expected
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
