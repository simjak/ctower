"""Canonical four-stage Proof-gated Workflow acceptance evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from support.server import (
    fixture_proof_policy,
    fixture_proof_store,
    running_api,
    start_and_admit,
)
from support.tenant_fixture import TenantFixture

from ctower_client import (
    AssignmentChangeRequest,
    AssignmentList,
    CtowerClient,
    CtowerProblemError,
    EvidenceRequest,
    FreezeCriteriaRequest,
    MutableAssignmentKind,
    Priority,
    Problem,
    ProofCriterion,
    ReopenIntent,
    ResolveCloseRequest,
    TicketCreateRequest,
    TicketIntentRequest,
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
from ctower_client import (
    WorkReceipt as HttpWorkReceipt,
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


@dataclass(frozen=True, slots=True)
class _OwnershipTrace:
    verdict: HttpProofReceipt
    terminal: HttpWorkflowReceipt
    closed: HttpWorkflowReceipt
    assignments: AssignmentList
    refused: Problem
    reopened: HttpWorkReceipt
    replay: Problem
    reassigned: HttpWorkReceipt
    hidden: Problem


class _AlwaysReady:
    def unmet_facts(
        self,
        connection: psycopg.Connection[dict[str, object]],
        tenant_id: UUID,
        ticket_id: UUID,
    ) -> tuple[str, ...]:
        del connection, tenant_id, ticket_id
        return ()


def test_generated_client_drives_the_four_stage_fixture(
    tenant: TenantFixture, second_tenant: TenantFixture
) -> None:
    candidate_digest = "sha256:" + "c" * 64
    content = "four-stage evidence"
    artifact_digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    with running_api(tenant.database.runtime_dsn) as base_url:
        with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
            prepared = _prepare_public_trace(
                commander, tenant, candidate_digest, artifact_digest, content
            )
        ownership = _exercise_ownership(
            base_url, tenant, second_tenant, prepared.ticket_id, candidate_digest
        )

    assert prepared.frame.stage == "frame"
    assert prepared.frozen.version == 1
    assert prepared.verification.activity_class == "verification"
    assert prepared.corrupt_code == "proof-evidence-digest-mismatch"
    assert prepared.evidence.version == prepared.frozen.version + 1
    assert prepared.self_review_code == "proof-self-review-refused"
    assert ownership.verdict.satisfied is True
    assert ownership.terminal.stage == "close"
    assert ownership.closed.lifecycle_facts == ("resolved", "closed")
    assert all(item.released_at is not None for item in ownership.assignments.assignments)
    assert ownership.refused.code == "work-ticket-terminal"
    assert ownership.replay == ownership.refused
    assert ownership.reopened.operation == "reopened"
    assert ownership.reassigned.operation == "assignment_changed"
    assert ownership.hidden.code == "tenant-scope-denied"


def _exercise_ownership(
    base_url: str,
    tenant: TenantFixture,
    second_tenant: TenantFixture,
    ticket_id: UUID,
    candidate_digest: str,
) -> _OwnershipTrace:
    with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
        commander.change_ticket_assignment(
            ticket_id,
            AssignmentChangeRequest(
                assignment_kind=MutableAssignmentKind.CURRENT_ASSIGNEE,
                expected_version=2,
                reason="Own the final candidate",
                to_principal_id=tenant.operator_id,
            ),
            command_id=uuid4(),
        )
    with CtowerClient(base_url, credential=tenant.operator_credential) as operator:
        verdict = operator.record_proof_verdict(
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
    with CtowerClient(base_url, credential=tenant.commander_credential) as commander:
        terminal, closed = _close_public_trace(commander, ticket_id)
        assignments = commander.list_ticket_assignments(ticket_id)
        refused_id = uuid4()
        request = AssignmentChangeRequest(
            assignment_kind=MutableAssignmentKind.CURRENT_ASSIGNEE,
            expected_version=3,
            reason="Closed ownership is forbidden",
            to_principal_id=tenant.commander_id,
        )
        refused = _problem(
            lambda: commander.change_ticket_assignment(ticket_id, request, command_id=refused_id)
        )
        reopened = commander.apply_ticket_intent(
            ticket_id,
            TicketIntentRequest(
                intent=ReopenIntent(
                    kind="reopen",
                    expected_version=3,
                    reason="A new episode is authorized",
                    priority_policy="carry_forward",
                )
            ),
            command_id=uuid4(),
        )
        replay = _problem(
            lambda: commander.change_ticket_assignment(ticket_id, request, command_id=refused_id)
        )
        reassigned = commander.change_ticket_assignment(
            ticket_id,
            request.model_copy(
                update={"expected_version": 4, "reason": "Own the reopened episode"}
            ),
            command_id=uuid4(),
        )
    with CtowerClient(base_url, credential=second_tenant.commander_credential) as foreign:
        hidden = _problem(lambda: foreign.list_ticket_assignments(ticket_id))
    return _OwnershipTrace(
        verdict, terminal, closed, assignments, refused, reopened, replay, reassigned, hidden
    )


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
                    description="Artifact evidence matches the current candidate.",
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
        workflow_ref=None,
        expected_version=2,
    )
    committed = workflow.resolve_close(workflow_actor, committed_close, telemetry=_telemetry())
    replay = workflow.resolve_close(workflow_actor, committed_close, telemetry=_telemetry())

    assert refused_replay == refused
    assert isinstance(committed, WorkflowReceipt)
    assert committed.workflow_ref == "fixture.atomic-close@1"
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
    criterion = Criterion(
        key="current",
        description="Evidence is current.",
        candidate_dependent=True,
        requires_verdict=True,
    )
    policy = fixture_proof_policy(
        "fixture.atomic-close@1",
        criterion,
    )
    proof_store = fixture_proof_store(tenant.database.runtime_dsn, policy)
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
            policy.gate_policy_ref: policy.gate_policy_digest,
            policy.evidence_policy_ref: policy.evidence_policy_digest,
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
            policy.gate_policy_ref,
            policy.gate_policy_digest,
            policy.evidence_policy_ref,
            policy.evidence_policy_digest,
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


def _problem[T](operation: Callable[[], T]) -> Problem:
    with pytest.raises(CtowerProblemError) as captured:
        operation()
    return Problem.model_validate(captured.value.problem)


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
