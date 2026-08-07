"""REVIEW transition dispatch intent, substrate consumption, and verdict join."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from support.server import application, fixture_proof_policy, running_api
from support.tenant_fixture import TenantFixture

from ctower_client import (
    AdmitIntent,
    ChangeReferenceRequest,
    CtowerClient,
    CtowerProblemError,
    EvidenceRequest,
    FreezeCriteriaRequest,
    Priority,
    ProofCriterion,
    ResolveCloseRequest,
    ReviewDispatchConsumeRequest,
    ReviewDispatchEffect,
    SessionStartRequest,
    SourceReference,
    TicketCreateRequest,
    TicketIntentRequest,
    VerdictDecision,
    VerdictRequest,
    WorkflowStartRequest,
    WorkflowTransitionRequest,
)
from ctower_kernel.proof import Criterion, ProofPolicy
from ctower_kernel.workflow import (
    ActivityClass,
    Stage,
    Transition,
    WorkflowEntryEffect,
    WorkflowGraph,
)

__all__: tuple[str, ...] = ()
_EXECUTION_DIGEST = "sha256:" + "1" * 64
_REVIEW_LENS_COUNT = 2


def test_review_transition_dispatch_consumption_and_verdict_link(
    tenant: TenantFixture,
) -> None:
    graph, policy = _review_contract()
    candidate_digest = "sha256:" + "a" * 64
    with (
        running_api(
            tenant.database.runtime_dsn,
            workflow_graph=graph,
            proof_policy_override=policy,
            execution_policy_digest=_EXECUTION_DIGEST,
        ) as base_url,
        CtowerClient(base_url, credential=tenant.commander_credential) as commander,
        CtowerClient(base_url, credential=tenant.operator_credential) as reviewer,
    ):
        _run_transcript(commander, reviewer, tenant, graph, policy, candidate_digest)


def test_in_process_review_dispatch_path_is_covered(tenant: TenantFixture) -> None:
    graph, policy = _review_contract()
    with TestClient(
        application(
            tenant.database.runtime_dsn,
            workflow_graph=graph,
            proof_policy_override=policy,
            execution_policy_digest=_EXECUTION_DIGEST,
        )
    ) as transport:
        commander = _transport_client(transport, tenant.commander_credential)
        reviewer = _transport_client(transport, tenant.operator_credential)
        _run_transcript(commander, reviewer, tenant, graph, policy, "sha256:" + "b" * 64)


def _run_transcript(
    commander: CtowerClient,
    reviewer: CtowerClient,
    tenant: TenantFixture,
    graph: WorkflowGraph,
    policy: ProofPolicy,
    candidate_digest: str,
) -> None:
    ticket_id = _prepare_ticket(commander, tenant, graph, policy)
    _freeze(commander, ticket_id, candidate_digest)
    effect = _enter_review_twice(commander, ticket_id, graph)
    _complete_proof(commander, reviewer, ticket_id, candidate_digest)
    _assert_close_waits_for_consumption(commander, ticket_id, graph)
    _consume_and_close(commander, tenant, ticket_id, graph, effect)


def _review_contract() -> tuple[WorkflowGraph, ProofPolicy]:
    graph = _review_graph()
    return graph, fixture_proof_policy(
        graph.reference,
        Criterion(
            "correctness",
            "The candidate is correct.",
            candidate_dependent=True,
            requires_verdict=True,
        ),
        Criterion(
            "security",
            "The candidate is secure.",
            candidate_dependent=True,
            requires_verdict=True,
        ),
    )


def _transport_client(transport: TestClient, credential: str) -> CtowerClient:
    client = CtowerClient(str(transport.base_url), credential=credential)
    client._http.close()
    client._http = transport
    return client


def _enter_review_twice(
    commander: CtowerClient, ticket_id: UUID, graph: WorkflowGraph
) -> ReviewDispatchEffect:
    commander.transition_workflow(
        ticket_id, _transition(graph, 1, "new", "build"), command_id=uuid4()
    )
    assert commander.list_review_dispatch_effects(ticket_id).effects == ()
    first_review = commander.transition_workflow(
        ticket_id, _transition(graph, 2, "build", "review"), command_id=uuid4()
    )
    effect = commander.list_review_dispatch_effects(ticket_id).effects[0]
    commander.transition_workflow(
        ticket_id, _transition(graph, 3, "review", "build"), command_id=uuid4()
    )
    commander.transition_workflow(
        ticket_id, _transition(graph, 4, "build", "review"), command_id=uuid4()
    )
    reentered = commander.list_review_dispatch_effects(ticket_id)
    assert first_review.stage == "review"
    assert len(reentered.effects) == 1
    assert effect.pr_reference == "https://github.com/simjak/ctower/pull/347"
    assert effect.lenses == ("correctness", "security")
    assert effect.author_model_ref == "openai/gpt-5-codex"
    assert effect.routing_policy_ref == "fixture.review-routing@1"
    assert effect.reviewer_family_rule == "different_from_author"
    return effect


def _assert_close_waits_for_consumption(
    commander: CtowerClient, ticket_id: UUID, graph: WorkflowGraph
) -> None:
    terminal = commander.transition_workflow(
        ticket_id, _transition(graph, 5, "review", "terminal"), command_id=uuid4()
    )
    with pytest.raises(CtowerProblemError) as incomplete:
        commander.resolve_close_workflow(
            ticket_id,
            ResolveCloseRequest(expected_version=6, workflow_ref=graph.reference),
            command_id=uuid4(),
        )
    assert terminal.stage == "terminal"
    assert incomplete.value.problem.code == "review-dispatch-incomplete"


def _consume_and_close(
    commander: CtowerClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    graph: WorkflowGraph,
    effect: ReviewDispatchEffect,
) -> None:
    with pytest.raises(CtowerProblemError) as same_family:
        commander.consume_review_dispatch_effect(
            ticket_id,
            effect.effect_id,
            _consume(tenant, author_family="codex", reviewer_family="codex"),
            command_id=uuid4(),
        )
    consumed = commander.consume_review_dispatch_effect(
        ticket_id,
        effect.effect_id,
        _consume(tenant, author_family="codex", reviewer_family="claude"),
        command_id=uuid4(),
    )
    linked = commander.list_review_dispatch_effects(ticket_id).effects[0]
    closed = commander.resolve_close_workflow(
        ticket_id,
        ResolveCloseRequest(expected_version=6, workflow_ref=graph.reference),
        command_id=uuid4(),
    )
    assert same_family.value.problem.code == "review-dispatch-family-conflict"
    assert consumed.operation == "assignment_changed"
    assert linked.status == "verdict_linked"
    assert linked.consumption is not None
    assert linked.consumption.reviewer_principal_id == tenant.operator_id
    assert linked.consumption.reviewer_family == "claude"
    assert len(linked.verdict_ids) == _REVIEW_LENS_COUNT
    assert closed.lifecycle_facts == ("resolved", "closed")


def _review_graph() -> WorkflowGraph:
    return WorkflowGraph(
        key="fixture.review-effect",
        revision=1,
        initial_stage="new",
        stages=(
            Stage("new", ActivityClass.WORK),
            Stage("build", ActivityClass.WORK),
            Stage(
                "review",
                ActivityClass.VERIFICATION,
                (WorkflowEntryEffect.REVIEW_CREW_DISPATCH,),
            ),
            Stage("terminal", ActivityClass.WORK),
        ),
        transitions=(
            Transition("new", "build", "entry.ready@1"),
            Transition("build", "review", "criteria.frozen@1"),
            Transition("review", "build", "entry.ready@1"),
            Transition("review", "terminal", "proof.current@1"),
        ),
        execution_policy_ref="fixture.review-routing@1",
        gate_policy_ref="fixture.gates@1",
        schema="ctower.workflow/v2",
    )


def _prepare_ticket(
    commander: CtowerClient,
    tenant: TenantFixture,
    graph: WorkflowGraph,
    policy: ProofPolicy,
) -> UUID:
    ticket_id = commander.create_ticket(
        TicketCreateRequest(
            initial_custodian_id=tenant.commander_id,
            priority=Priority.P1,
            project_key="ctower",
            source=SourceReference(kind="github", ref="gh#347"),
            title="Review dispatch effect acceptance",
        ),
        command_id=uuid4(),
    ).ticket.ticket_id
    commander.start_ticket_workflow(
        ticket_id,
        WorkflowStartRequest(
            workflow_ref=graph.reference,
            workflow_digest=graph.digest,
            execution_policy_ref="fixture.review-routing@1",
            execution_policy_digest=_EXECUTION_DIGEST,
            gate_policy_ref=policy.gate_policy_ref,
            gate_policy_digest=policy.gate_policy_digest,
            evidence_policy_ref=policy.evidence_policy_ref,
            evidence_policy_digest=policy.evidence_policy_digest,
        ),
        command_id=uuid4(),
    )
    commander.apply_ticket_intent(
        ticket_id,
        TicketIntentRequest(
            intent=AdmitIntent(kind="admit", expected_version=1, reason="Ready for work")
        ),
        command_id=uuid4(),
    )
    commander.start_ticket_session(
        ticket_id,
        SessionStartRequest(
            branch_ref="feat/347-review-effect",
            crew_name="engineer-r347-review-effect",
            harness_ref="codex",
            model_ref="openai/gpt-5-codex",
            seat_key="ctower-commander",
            worktree_ref="worktree:r347-review-effect",
        ),
        command_id=uuid4(),
    )
    commander.record_ticket_change_reference(
        ticket_id,
        ChangeReferenceRequest(
            repository="simjak/ctower",
            change_identity="347",
            reference="https://github.com/simjak/ctower/pull/347",
        ),
        command_id=uuid4(),
    )
    return ticket_id


def _freeze(commander: CtowerClient, ticket_id: UUID, candidate_digest: str) -> None:
    commander.freeze_proof_criteria(
        ticket_id,
        FreezeCriteriaRequest(
            expected_version=0,
            candidate_digest=candidate_digest,
            criteria=(
                ProofCriterion(
                    key="correctness",
                    description="The candidate is correct.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
                ProofCriterion(
                    key="security",
                    description="The candidate is secure.",
                    candidate_dependent=True,
                    requires_verdict=True,
                ),
            ),
        ),
        command_id=uuid4(),
    )


def _complete_proof(
    commander: CtowerClient,
    reviewer: CtowerClient,
    ticket_id: UUID,
    candidate_digest: str,
) -> None:
    version = 1
    for lens in ("correctness", "security"):
        content = f"{lens} evidence"
        commander.record_proof_evidence(
            ticket_id,
            EvidenceRequest(
                expected_version=version,
                evidence_id=uuid4(),
                criterion_key=lens,
                candidate_digest=candidate_digest,
                artifact_digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
                content=content,
            ),
            command_id=uuid4(),
        )
        version += 1
    for lens in ("correctness", "security"):
        reviewer.record_proof_verdict(
            ticket_id,
            VerdictRequest(
                expected_version=version,
                verdict_id=uuid4(),
                criterion_key=lens,
                candidate_digest=candidate_digest,
                decision=VerdictDecision.PASS,
            ),
            command_id=uuid4(),
        )
        version += 1


def _transition(
    graph: WorkflowGraph, expected_version: int, source: str, destination: str
) -> WorkflowTransitionRequest:
    return WorkflowTransitionRequest(
        expected_version=expected_version,
        workflow_ref=graph.reference,
        source_stage=source,
        destination_stage=destination,
    )


def _consume(
    tenant: TenantFixture, *, author_family: str, reviewer_family: str
) -> ReviewDispatchConsumeRequest:
    return ReviewDispatchConsumeRequest(
        expected_version=3,
        reason="Route an independent review crew",
        reviewer_principal_id=tenant.operator_id,
        author_family=author_family,
        reviewer_family=reviewer_family,
        crew_name="review-r347-review-effect",
    )
