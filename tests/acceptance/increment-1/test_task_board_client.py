"""Generated-client CP2 ticket, Board, Proof, and linked-audit journey."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from support.acceptance import accept_pending_commands
from support.server import running_api
from support.tenant_fixture import TenantFixture, create_second_tenant

from ctower_client import (
    AdmitIntent,
    AssignmentChangeRequest,
    AuditEvent,
    BlockIntent,
    BoardLane,
    BoardView,
    CtowerClient,
    CtowerProblemError,
    EvidenceRequest,
    FreezeCriteriaRequest,
    MutableAssignmentKind,
    Priority,
    PriorityChangeRequest,
    ProjectionHealth,
    ProofCriterion,
    RelationKind,
    RelationRequest,
    ReopenIntent,
    ResolveCloseRequest,
    SourceReference,
    TicketCreateRequest,
    TicketIntentRequest,
    UnblockIntent,
    VerdictDecision,
    VerdictRequest,
    WorkflowStartRequest,
    WorkflowTransitionRequest,
)
from ctower_client import (
    Problem as HttpProblem,
)
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.workflow import WorkflowGraph

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()
REOPENED_WORK_VERSION = 8
CUSTODY_EPISODE_COUNT = 2
PROOF_EVENT_COUNT = 3
HTTP_NOT_FOUND = 404


def test_generated_client_drives_complete_task_board_and_audit_flow(
    tenant: TenantFixture,
) -> None:
    graph = _graph()
    with running_api(
        tenant.database.runtime_dsn, projection_dsn=tenant.database.projection_dsn
    ) as base_url:
        commander = CtowerClient(base_url, credential=tenant.commander_credential)
        operator = CtowerClient(base_url, credential=tenant.operator_credential)
        ticket_id = _new_ticket(commander, tenant.commander_id, "cp2-client")
        assert _refresh_board(tenant, commander).cards[0].lane is BoardLane.BACKLOG
        with pytest.raises(CtowerProblemError) as invalid_filter:
            commander.get_board(project_key="ctower", stage_key="NOT A STAGE")
        assert invalid_filter.value.problem.code == "validation-error"
        _start_and_admit(commander, ticket_id, graph, tenant)
        _prioritize_assign_and_begin(commander, ticket_id, tenant, graph)
        _block_and_unblock(commander, ticket_id, tenant.commander_id, tenant)
        _finish_proof_and_workflow(commander, operator, ticket_id, graph, tenant)
        _assert_close_reopen_custody(commander, ticket_id, tenant)
        fresh_run = commander.start_ticket_workflow(ticket_id, _start(graph), command_id=uuid4())
        pages = _audit_pages(commander, ticket_id)
        commander.close()
        operator.close()

    assert fresh_run.version == 1
    assert len([event for event in pages if event.kind == "proof.changed"]) == PROOF_EVENT_COUNT
    assert len({event.event_id for event in pages}) == len(pages)
    assert {event.kind for event in pages} >= {
        "ticket.created",
        "work.changed",
        "workflow.changed",
        "proof.changed",
    }


def _assert_close_reopen_custody(
    client: CtowerClient, ticket_id: UUID, tenant: TenantFixture
) -> None:
    complete = _refresh_board(tenant, client)
    closed = tuple(
        interval
        for interval in client.list_ticket_assignments(ticket_id, project_key="ctower").assignments
        if interval.assignment_kind.value == "ticket_custodian"
    )
    reopened_receipt = client.apply_ticket_intent(
        ticket_id,
        TicketIntentRequest(
            intent=ReopenIntent(
                kind="reopen",
                expected_version=7,
                reason="A new actionable episode is required",
                priority_policy="carry_forward",
            )
        ),
        command_id=uuid4(),
    )
    reopened = _refresh_board(tenant, client)
    history = tuple(
        interval
        for interval in client.list_ticket_assignments(ticket_id, project_key="ctower").assignments
        if interval.assignment_kind.value == "ticket_custodian"
    )
    assert complete.cards[0].lane is BoardLane.COMPLETE
    assert len(closed) == 1 and closed[0].released_at is not None
    assert closed[0].episode_number == 1
    assert reopened_receipt.version == REOPENED_WORK_VERSION
    assert reopened.cards[0].lane is BoardLane.BACKLOG
    assert len(history) == CUSTODY_EPISODE_COUNT
    assert [item.episode_number for item in history] == [1, CUSTODY_EPISODE_COUNT]
    prior_release = history[0].released_at
    assert prior_release is not None and prior_release <= history[1].assigned_at
    assert history[1].released_at is None


def _start_and_admit(
    client: CtowerClient,
    ticket_id: UUID,
    graph: WorkflowGraph,
    tenant: TenantFixture,
) -> None:
    client.start_ticket_workflow(ticket_id, _start(graph), command_id=uuid4())
    client.apply_ticket_intent(
        ticket_id,
        TicketIntentRequest(
            intent=AdmitIntent(kind="admit", expected_version=1, reason="Ready for capacity")
        ),
        command_id=uuid4(),
    )
    ready = _refresh_board(tenant, client)
    assert ready.health is ProjectionHealth.CURRENT
    assert ready.cards[0].lane is BoardLane.READY


def _prioritize_assign_and_begin(
    client: CtowerClient, ticket_id: UUID, tenant: TenantFixture, graph: WorkflowGraph
) -> None:
    client.change_ticket_priority(
        ticket_id,
        PriorityChangeRequest(expected_version=2, priority=Priority.P1, reason="Customer impact"),
        command_id=uuid4(),
    )
    for version, principal, reason in (
        (3, tenant.commander_id, "Begin implementation"),
        (4, tenant.operator_id, "Continue implementation"),
    ):
        client.change_ticket_assignment(
            ticket_id,
            AssignmentChangeRequest(
                assignment_kind=MutableAssignmentKind.CURRENT_ASSIGNEE,
                expected_version=version,
                reason=reason,
                to_principal_id=principal,
            ),
            command_id=uuid4(),
        )
    assignments = client.list_ticket_assignments(ticket_id, project_key="ctower").assignments
    assert assignments[0].assignment_kind.value == "current_assignee"
    assert assignments[0].released_at == assignments[1].assigned_at
    assert assignments[1].released_at is None
    client.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=1,
            workflow_ref=graph.reference,
            source_stage="capture",
            destination_stage="frame",
        ),
        command_id=uuid4(),
    )
    assert _refresh_board(tenant, client).cards[0].lane is BoardLane.IN_PROGRESS


def _block_and_unblock(
    client: CtowerClient,
    ticket_id: UUID,
    owner_id: UUID,
    tenant: TenantFixture,
) -> None:
    blocker_id = uuid4()
    client.apply_ticket_intent(
        ticket_id,
        TicketIntentRequest(
            intent=BlockIntent(
                kind="block",
                expected_version=5,
                reason="Dependency unavailable",
                blocker_id=blocker_id,
                blocker_kind="dependency",
                reason_class="external_dependency",
                owner_principal_id=owner_id,
                source_ref="test:blocker",
                affected_stage="frame",
                resolution_condition="Dependency is restored",
                next_check_at=datetime.now(UTC) + timedelta(hours=1),
                dependency_ref="ticket:dependency",
                board_impact=True,
            )
        ),
        command_id=uuid4(),
    )
    blocked = _refresh_board(tenant, client).cards[0]
    assert blocked.lane is BoardLane.BLOCKED
    assert blocked.underlying_lane == "in_progress"
    client.apply_ticket_intent(
        ticket_id,
        TicketIntentRequest(
            intent=UnblockIntent(
                kind="unblock",
                expected_version=6,
                reason="Dependency restored",
                blocker_id=blocker_id,
                resolution_evidence_ref="proof:dependency",
            )
        ),
        command_id=uuid4(),
    )


def test_generated_client_refuses_relation_cycles_and_cross_tenant_targets(
    tenant: TenantFixture,
) -> None:
    other = create_second_tenant(tenant.database)
    with running_api(tenant.database.runtime_dsn) as base_url:
        client = CtowerClient(base_url, credential=tenant.commander_credential)
        other_client = CtowerClient(base_url, credential=other.commander_credential)
        source = _new_ticket(client, tenant.commander_id, "relation-source")
        target = _new_ticket(client, tenant.commander_id, "relation-target")
        foreign = _new_ticket(other_client, other.commander_id, "relation-foreign")
        with pytest.raises(CtowerProblemError) as hidden:
            client.add_ticket_relation(
                source,
                RelationRequest(
                    expected_version=1,
                    reason="Must remain hidden",
                    relation_kind=RelationKind.DEPENDS_ON,
                    target_ticket_id=foreign,
                ),
                command_id=uuid4(),
            )
        client.add_ticket_relation(
            source,
            RelationRequest(
                expected_version=1,
                reason="Source depends on target",
                relation_kind=RelationKind.DEPENDS_ON,
                target_ticket_id=target,
            ),
            command_id=uuid4(),
        )
        with pytest.raises(CtowerProblemError) as cycle:
            client.add_ticket_relation(
                target,
                RelationRequest(
                    expected_version=1,
                    reason="Would create a cycle",
                    relation_kind=RelationKind.DEPENDS_ON,
                    target_ticket_id=source,
                ),
                command_id=uuid4(),
            )
        client.close()
        other_client.close()

    assert cast(HttpProblem, hidden.value.problem).status == HTTP_NOT_FOUND
    assert hidden.value.problem.code == "tenant-scope-denied"
    assert cycle.value.problem.code == "work-relation-cycle"


def test_generated_board_source_lookup_returns_hit_and_empty_miss(
    tenant: TenantFixture,
) -> None:
    source_ref = "R2238"
    with running_api(
        tenant.database.runtime_dsn, projection_dsn=tenant.database.projection_dsn
    ) as base_url:
        client = CtowerClient(base_url, credential=tenant.commander_credential)
        created = client.create_ticket(
            TicketCreateRequest(
                initial_custodian_id=tenant.commander_id,
                priority=Priority.P2,
                project_key="ctower",
                source=SourceReference(kind="mission-control", ref=source_ref),
                title="Source lookup acceptance",
            ),
            command_id=uuid4(),
        )
        _refresh_board(tenant, client)
        hit = client.get_board(
            project_key="ctower", source_kind="mission-control", source_ref=source_ref
        )
        miss = client.get_board(project_key="ctower", source_ref="R-does-not-exist")
        client.close()

    assert [card.ticket_id for card in hit.cards] == [created.ticket.ticket_id]
    assert miss.cards == ()


def _new_ticket(client: CtowerClient, custodian_id: UUID, suffix: str) -> UUID:
    return client.create_ticket(
        TicketCreateRequest(
            initial_custodian_id=custodian_id,
            priority=Priority.P2,
            project_key="ctower",
            source=SourceReference(kind="test", ref=f"test:{suffix}:{uuid4()}"),
            title=suffix,
        ),
        command_id=uuid4(),
    ).ticket.ticket_id


def _finish_proof_and_workflow(
    commander: CtowerClient,
    operator: CtowerClient,
    ticket_id: UUID,
    graph: WorkflowGraph,
    tenant: TenantFixture,
) -> None:
    candidate = "sha256:" + "c" * 64
    content = "current CP2 evidence"
    artifact = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
    _freeze_criterion(commander, ticket_id, candidate)
    commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=2,
            workflow_ref=graph.reference,
            source_stage="frame",
            destination_stage="verify",
        ),
        command_id=uuid4(),
    )
    assert _refresh_board(tenant, commander).cards[0].lane is BoardLane.IN_REVIEW
    commander.record_proof_evidence(
        ticket_id,
        EvidenceRequest(
            expected_version=1,
            evidence_id=uuid4(),
            criterion_key="artifact-current",
            candidate_digest=candidate,
            artifact_digest=artifact,
            content=content,
        ),
        command_id=uuid4(),
    )
    operator.record_proof_verdict(
        ticket_id,
        VerdictRequest(
            expected_version=2,
            verdict_id=uuid4(),
            criterion_key="artifact-current",
            candidate_digest=candidate,
            decision=VerdictDecision.PASS,
        ),
        command_id=uuid4(),
    )
    commander.transition_workflow(
        ticket_id,
        WorkflowTransitionRequest(
            expected_version=3,
            workflow_ref=graph.reference,
            source_stage="verify",
            destination_stage="close",
        ),
        command_id=uuid4(),
    )
    commander.resolve_close_workflow(
        ticket_id,
        ResolveCloseRequest(expected_version=4, workflow_ref=graph.reference),
        command_id=uuid4(),
    )


def _freeze_criterion(client: CtowerClient, ticket_id: UUID, candidate: str) -> None:
    client.freeze_proof_criteria(
        ticket_id,
        FreezeCriteriaRequest(
            expected_version=0,
            candidate_digest=candidate,
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


def _audit_pages(client: CtowerClient, ticket_id: UUID) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    cursor = 0
    while True:
        page = client.list_ticket_audit_events(
            ticket_id, project_key="ctower", cursor=cursor, limit=2
        )
        events.extend(page.events)
        if page.next_cursor is None:
            return events
        cursor = page.next_cursor


def _graph() -> WorkflowGraph:
    payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    return WorkflowGraph.from_mapping(payload)


def _start(graph: WorkflowGraph) -> WorkflowStartRequest:
    return WorkflowStartRequest(
        workflow_ref=graph.reference,
        workflow_digest=graph.digest,
        execution_policy_ref="ctower.trust-spine-four-stage.execution@1",
        execution_policy_digest=_digest("packs/policies/execution/trust-spine-four-stage-v1.yaml"),
        gate_policy_ref="ctower.trust-spine-four-stage.gates@1",
        gate_policy_digest=_digest("packs/policies/gates/trust-spine-four-stage-v1.yaml"),
        evidence_policy_ref="ctower.trust-spine-four-stage.evidence@1",
        evidence_policy_digest=_digest("packs/policies/evidence/trust-spine-four-stage-v1.yaml"),
    )


def _digest(relative: str) -> str:
    return f"sha256:{hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()}"


def _refresh_board(tenant: TenantFixture, client: CtowerClient) -> BoardView:
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(tenant.tenant_id)
    return client.get_board(project_key="ctower")
