"""Explicit Workflow start/pin and Work axis acceptance tracers."""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from support.tenant_fixture import TenantFixture

from ctower_kernel.proof.postgres import PostgresProof
from ctower_kernel.record import (
    Actor,
    AuditEvent,
    PrincipalKind,
    RecordProblem,
    SourceReference,
    TicketCommand,
)
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import (
    Admit,
    AssignmentKind,
    Block,
    ChangeAssignment,
    ChangePriority,
    Unblock,
    Work,
    WorkReadiness,
    WorkReceipt,
)
from ctower_kernel.work.postgres import PostgresWork
from ctower_kernel.workflow import (
    Workflow,
    WorkflowActor,
    WorkflowGraph,
    WorkflowMutation,
    WorkflowReceipt,
    WorkflowStart,
)
from ctower_kernel.workflow.postgres import PostgresWorkflow

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()
FIRST_CHANGE_VERSION = 2
ASSIGNMENT_WORK_VERSION = 4
BLOCKER_WORK_VERSION = 6
REFUSAL_COMMAND_COUNT = 2
HTTP_CONFLICT = 409


def test_work_and_workflow_refusals_replay_before_later_state_reads(
    tenant: TenantFixture,
) -> None:
    graph = _graph()
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    workflow_actor = WorkflowActor(tenant.commander_id, tenant.tenant_id)
    record = PostgresRecord(tenant.database.runtime_dsn)
    work = Work(record, writer=PostgresWork(tenant.database.runtime_dsn))
    workflow = Workflow(
        (graph,),
        writer=PostgresWorkflow(
            tenant.database.runtime_dsn,
            proof_gate=PostgresProof(tenant.database.runtime_dsn),
            readiness_gate=PostgresWork(tenant.database.runtime_dsn),
        ),
        policy_digests=_policy_digests(),
    )
    work_command_id = _assert_work_refusal_replay(tenant, work, actor)
    workflow_command_id = _assert_workflow_refusal_replay(
        tenant, work, actor, workflow, workflow_actor, graph
    )

    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        rows = connection.execute(
            """
            SELECT client_command_id, status_code, response_body, event_ids
            FROM command_results WHERE client_command_id = ANY(%s)
            ORDER BY client_command_id
            """,
            ([work_command_id, workflow_command_id],),
        ).fetchall()
        event_count_row = connection.execute(
            "SELECT count(*) AS value FROM events WHERE client_command_id = ANY(%s)",
            ([work_command_id, workflow_command_id],),
        ).fetchone()
    assert event_count_row is not None
    event_count = event_count_row["value"]
    assert len(rows) == REFUSAL_COMMAND_COUNT
    assert all(row["status_code"] == HTTP_CONFLICT for row in rows)
    assert all(row["event_ids"] == [] for row in rows)
    assert event_count == 0


def _assert_work_refusal_replay(tenant: TenantFixture, work: Work, actor: Actor) -> UUID:
    ticket_id = _ticket(tenant)
    command_id = uuid4()
    refused = ChangePriority(command_id, ticket_id, 2, "Refuse before later state", "P1")
    first = work.execute(actor, refused, telemetry=_telemetry())
    advanced = work.execute(
        actor,
        ChangePriority(uuid4(), ticket_id, 1, "Advance independently", "P1"),
        telemetry=_telemetry(),
    )
    replayed = work.execute(actor, refused, telemetry=_telemetry())
    changed = work.execute(
        actor, replace(refused, reason="Changed reuse body"), telemetry=_telemetry()
    )
    assert isinstance(first, RecordProblem) and first.current_version == 1
    assert isinstance(advanced, WorkReceipt)
    assert replayed == first
    assert isinstance(changed, RecordProblem) and changed.code == "idempotency-conflict"
    return command_id


def _assert_workflow_refusal_replay(
    tenant: TenantFixture,
    work: Work,
    actor: Actor,
    workflow: Workflow,
    workflow_actor: WorkflowActor,
    graph: WorkflowGraph,
) -> UUID:
    ticket_id = _ticket(tenant)
    workflow.start(workflow_actor, _start(graph, ticket_id), telemetry=_telemetry())
    admitted = work.execute(
        actor,
        Admit(uuid4(), ticket_id, 1, "Ready for independent transition"),
        telemetry=_telemetry(),
    )
    command_id = uuid4()
    refused = WorkflowMutation(command_id, ticket_id, graph.reference, 2, "capture", "frame")
    first = workflow.advance(workflow_actor, refused, telemetry=_telemetry())
    advanced = workflow.advance(
        workflow_actor,
        WorkflowMutation(uuid4(), ticket_id, graph.reference, 1, "capture", "frame"),
        telemetry=_telemetry(),
    )
    replayed = workflow.advance(workflow_actor, refused, telemetry=_telemetry())
    changed = workflow.advance(
        workflow_actor, replace(refused, expected_version=3), telemetry=_telemetry()
    )
    assert isinstance(admitted, WorkReceipt)
    assert isinstance(first, RecordProblem) and first.current_version == 1
    assert isinstance(advanced, WorkflowReceipt)
    assert replayed == first
    assert isinstance(changed, RecordProblem) and changed.code == "idempotency-conflict"
    return command_id


def test_workflow_requires_exact_explicit_pin_and_replays_start(tenant: TenantFixture) -> None:
    graph = _graph()
    store = PostgresWorkflow(
        tenant.database.runtime_dsn,
        proof_gate=PostgresProof(tenant.database.runtime_dsn),
        readiness_gate=PostgresWork(tenant.database.runtime_dsn),
    )
    workflow = Workflow((graph,), writer=store, policy_digests=_policy_digests())
    actor = WorkflowActor(tenant.commander_id, tenant.tenant_id)
    ticket_id = _ticket(tenant)
    absent_ticket_id = _ticket(tenant)
    command = _start(graph, ticket_id)

    absent = workflow.advance(
        actor,
        WorkflowMutation(uuid4(), absent_ticket_id, graph.reference, 0, "capture", "frame"),
        telemetry=_telemetry(),
    )
    wrong_digest = workflow.start(
        actor,
        replace(
            command,
            client_command_id=uuid4(),
            workflow_digest="sha256:" + "f" * 64,
        ),
        telemetry=_telemetry(),
    )
    started = workflow.start(actor, command, telemetry=_telemetry())
    replay = workflow.start(actor, command, telemetry=_telemetry())
    second = workflow.start(actor, _start(graph, ticket_id), telemetry=_telemetry())
    altered = Workflow(
        (replace(graph, initial_stage="frame"),),
        writer=store,
        policy_digests=_policy_digests(),
    ).advance(
        actor,
        WorkflowMutation(uuid4(), ticket_id, graph.reference, 1, "capture", "frame"),
        telemetry=_telemetry(),
    )
    assert isinstance(absent, RecordProblem)
    assert absent.code == "workflow-run-not-started"
    assert isinstance(wrong_digest, RecordProblem)
    assert wrong_digest.code == "workflow-pin-mismatch"
    assert isinstance(started, WorkflowReceipt)
    assert started.stage == "capture"
    assert started.version == 1
    assert replay == started
    assert isinstance(second, RecordProblem)
    assert second.code == "workflow-already-started"
    assert isinstance(altered, RecordProblem)
    assert altered.code == "workflow-pin-mismatch"


def test_workflow_rechecks_work_readiness_before_transition(tenant: TenantFixture) -> None:
    graph = _graph()
    store = PostgresWorkflow(
        tenant.database.runtime_dsn,
        proof_gate=PostgresProof(tenant.database.runtime_dsn),
        readiness_gate=PostgresWork(tenant.database.runtime_dsn),
    )
    workflow = Workflow((graph,), writer=store, policy_digests=_policy_digests())
    actor = WorkflowActor(tenant.commander_id, tenant.tenant_id)
    ticket_id = _ticket(tenant)
    workflow.start(actor, _start(graph, ticket_id), telemetry=_telemetry())
    not_admitted = workflow.advance(
        actor,
        WorkflowMutation(uuid4(), ticket_id, graph.reference, 1, "capture", "frame"),
        telemetry=_telemetry(),
    )
    record = PostgresRecord(tenant.database.runtime_dsn)
    work = Work(record, writer=PostgresWork(tenant.database.runtime_dsn))
    work_actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    admitted = work.execute(
        work_actor,
        Admit(uuid4(), ticket_id, 1, "Ready for Workflow"),
        telemetry=_telemetry(),
    )
    before_refusal = record.get_ticket(work_actor, ticket_id, "ctower", telemetry=_telemetry())
    repeated_admit = work.execute(
        work_actor,
        Admit(uuid4(), ticket_id, 2, "Already active"),
        telemetry=_telemetry(),
    )
    after_refusal = record.get_ticket(work_actor, ticket_id, "ctower", telemetry=_telemetry())
    moved = workflow.advance(
        actor,
        WorkflowMutation(uuid4(), ticket_id, graph.reference, 1, "capture", "frame"),
        telemetry=_telemetry(),
    )

    assert isinstance(not_admitted, RecordProblem)
    assert not_admitted.unmet_facts == ("work.admitted@1",)
    assert isinstance(admitted, WorkReceipt)
    assert admitted.version == FIRST_CHANGE_VERSION
    assert isinstance(repeated_admit, RecordProblem)
    assert repeated_admit.unmet_facts == ("lifecycle.open-or-waiting@1",)
    assert before_refusal == after_refusal
    assert isinstance(moved, WorkflowReceipt)
    assert moved.version == FIRST_CHANGE_VERSION


def test_work_priority_assignment_replay_and_orthogonal_custody(
    tenant: TenantFixture,
) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    record = PostgresRecord(tenant.database.runtime_dsn)
    writer = PostgresWork(tenant.database.runtime_dsn)
    work = Work(record, writer=writer)
    ticket_id = _ticket(tenant)
    priority = ChangePriority(
        client_command_id=uuid4(),
        ticket_id=ticket_id,
        expected_version=1,
        reason="Customer impact",
        priority="P1",
    )

    prioritized = work.execute(actor, priority, telemetry=_telemetry())
    assigned, reassigned = _assign_twice(work, actor, ticket_id, tenant)
    replay = work.execute(actor, priority, telemetry=_telemetry())
    conflict = work.execute(actor, replace(priority, priority="P2"), telemetry=_telemetry())
    history = work.assignments(actor, ticket_id, "ctower")
    ticket = record.get_ticket(actor, ticket_id, "ctower", telemetry=_telemetry())
    audit_events = _audit_events(record, actor, ticket_id)

    assert all(isinstance(outcome, WorkReceipt) for outcome in (prioritized, assigned, reassigned))
    assert replay == prioritized
    assert isinstance(conflict, RecordProblem)
    assert conflict.code == "idempotency-conflict"
    assert not isinstance(history, RecordProblem)
    assert [item.assignment_kind for item in history] == [
        AssignmentKind.CURRENT_ASSIGNEE,
        AssignmentKind.CURRENT_ASSIGNEE,
        AssignmentKind.TICKET_CUSTODIAN,
    ]
    assert history[0].released_at == history[1].assigned_at
    assert history[1].released_at is None
    assert not isinstance(ticket, RecordProblem)
    assert ticket.custodian_id == tenant.commander_id
    assert ticket.version == ASSIGNMENT_WORK_VERSION
    assert len(audit_events) == ASSIGNMENT_WORK_VERSION
    assert len({event.event_id for event in audit_events}) == len(audit_events)
    assert [event.record_position for event in audit_events] == sorted(
        event.record_position for event in audit_events
    )


def test_work_multi_blocker_requires_every_effective_blocker_to_clear(
    tenant: TenantFixture,
) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    record = PostgresRecord(tenant.database.runtime_dsn)
    work = Work(record, writer=PostgresWork(tenant.database.runtime_dsn))
    ticket_id = _ticket(tenant)
    admitted = work.execute(
        actor,
        Admit(uuid4(), ticket_id, 1, "Ready for capacity"),
        telemetry=_telemetry(),
    )
    outcomes, still_blocked, ready = _exercise_two_blockers(work, actor, ticket_id, tenant)
    ticket = record.get_ticket(actor, ticket_id, "ctower", telemetry=_telemetry())
    audit_events = _audit_events(record, actor, ticket_id)

    assert isinstance(admitted, WorkReceipt)
    assert all(isinstance(outcome, WorkReceipt) for outcome in outcomes)
    assert not isinstance(still_blocked, RecordProblem)
    assert not isinstance(ready, RecordProblem)
    assert still_blocked.ready is False
    assert ready.ready is True
    assert not isinstance(ticket, RecordProblem)
    assert ticket.version == BLOCKER_WORK_VERSION
    assert len(audit_events) == BLOCKER_WORK_VERSION


def _assign_twice(
    work: Work, actor: Actor, ticket_id: UUID, tenant: TenantFixture
) -> tuple[WorkReceipt | RecordProblem, WorkReceipt | RecordProblem]:
    assigned = work.execute(
        actor,
        ChangeAssignment(
            uuid4(),
            ticket_id,
            2,
            "Begin work",
            AssignmentKind.CURRENT_ASSIGNEE,
            tenant.operator_id,
        ),
        telemetry=_telemetry(),
    )
    reassigned = work.execute(
        actor,
        ChangeAssignment(
            uuid4(),
            ticket_id,
            3,
            "Continue work",
            AssignmentKind.CURRENT_ASSIGNEE,
            tenant.commander_id,
        ),
        telemetry=_telemetry(),
    )
    return assigned, reassigned


def _exercise_two_blockers(
    work: Work, actor: Actor, ticket_id: UUID, tenant: TenantFixture
) -> tuple[
    tuple[WorkReceipt | RecordProblem, ...],
    WorkReadiness | RecordProblem,
    WorkReadiness | RecordProblem,
]:
    first_id, second_id = uuid4(), uuid4()
    first = work.execute(
        actor, _block(ticket_id, first_id, 2, tenant.operator_id), telemetry=_telemetry()
    )
    second = work.execute(
        actor, _block(ticket_id, second_id, 3, tenant.operator_id), telemetry=_telemetry()
    )
    one_cleared = work.execute(
        actor,
        Unblock(uuid4(), ticket_id, 4, "Dependency arrived", first_id, "proof:first"),
        telemetry=_telemetry(),
    )
    still_blocked = work.readiness(actor, ticket_id)
    all_cleared = work.execute(
        actor,
        Unblock(uuid4(), ticket_id, 5, "Capacity restored", second_id, "proof:second"),
        telemetry=_telemetry(),
    )
    ready = work.readiness(actor, ticket_id)
    return (first, second, one_cleared, all_cleared), still_blocked, ready


def _audit_events(record: PostgresRecord, actor: Actor, ticket_id: UUID) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    cursor = 0
    while True:
        page = record.ticket_audit(
            actor, ticket_id, "ctower", cursor=cursor, limit=2, telemetry=_telemetry()
        )
        assert not isinstance(page, RecordProblem)
        events.extend(page.events)
        if page.next_cursor is None:
            return events
        cursor = page.next_cursor


@pytest.mark.parametrize("operation", ("priority", "assignment"))
def test_concurrent_work_commands_have_one_cas_winner(
    tenant: TenantFixture, operation: str
) -> None:
    actor = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    ticket_id = _ticket(tenant)
    commands: tuple[ChangePriority | ChangeAssignment, ChangePriority | ChangeAssignment]
    if operation == "priority":
        commands = (
            ChangePriority(uuid4(), ticket_id, 1, "First priority", "P1"),
            ChangePriority(uuid4(), ticket_id, 1, "Second priority", "P0"),
        )
    else:
        commands = (
            ChangeAssignment(
                uuid4(),
                ticket_id,
                1,
                "First assignment",
                AssignmentKind.CURRENT_ASSIGNEE,
                tenant.commander_id,
            ),
            ChangeAssignment(
                uuid4(),
                ticket_id,
                1,
                "Second assignment",
                AssignmentKind.CURRENT_ASSIGNEE,
                tenant.operator_id,
            ),
        )
    barrier = threading.Barrier(2)

    def execute(command: ChangePriority | ChangeAssignment) -> WorkReceipt | RecordProblem:
        barrier.wait()
        return Work(
            PostgresRecord(tenant.database.runtime_dsn),
            writer=PostgresWork(tenant.database.runtime_dsn),
        ).execute(actor, command, telemetry=_telemetry())

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = tuple(pool.map(execute, commands))

    assert sum(isinstance(outcome, WorkReceipt) for outcome in outcomes) == 1
    conflicts = tuple(outcome for outcome in outcomes if isinstance(outcome, RecordProblem))
    assert len(conflicts) == 1
    assert conflicts[0].code == "version-conflict"
    if operation == "assignment":
        history = Work(
            PostgresRecord(tenant.database.runtime_dsn),
            writer=PostgresWork(tenant.database.runtime_dsn),
        ).assignments(actor, ticket_id, "ctower")
        assert not isinstance(history, RecordProblem)
        current = tuple(
            interval
            for interval in history
            if interval.assignment_kind is AssignmentKind.CURRENT_ASSIGNEE
            and interval.released_at is None
        )
        assert len(current) == 1


def _block(ticket_id: UUID, blocker_id: UUID, version: int, owner_id: UUID) -> Block:
    return Block(
        client_command_id=uuid4(),
        ticket_id=ticket_id,
        expected_version=version,
        reason="External dependency",
        blocker_id=blocker_id,
        blocker_kind="dependency",
        reason_class="external_dependency",
        owner_principal_id=owner_id,
        source_ref="test:blocker",
        affected_stage="capture",
        resolution_condition="Dependency is available",
        next_check_at=datetime.now(UTC) + timedelta(hours=1),
        dependency_ref="ticket:external",
        board_impact=True,
    )


def _graph() -> WorkflowGraph:
    payload = json.loads(
        (ROOT / "packs/workflows/ctower.trust-spine-four-stage/v1.yaml").read_text(encoding="utf-8")
    )
    return WorkflowGraph.from_mapping(payload)


def _start(graph: WorkflowGraph, ticket_id: UUID) -> WorkflowStart:
    return WorkflowStart(
        client_command_id=uuid4(),
        ticket_id=ticket_id,
        workflow_ref=graph.reference,
        workflow_digest=graph.digest,
        execution_policy_ref="ctower.trust-spine-four-stage.execution@1",
        execution_policy_digest=_file_digest(
            "packs/policies/execution/trust-spine-four-stage-v1.yaml"
        ),
        gate_policy_ref="ctower.trust-spine-four-stage.gates@1",
        gate_policy_digest=_file_digest("packs/policies/gates/trust-spine-four-stage-v1.yaml"),
        evidence_policy_ref="ctower.trust-spine-four-stage.evidence@1",
        evidence_policy_digest=_file_digest(
            "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
        ),
    )


def _file_digest(relative: str) -> str:
    return f"sha256:{hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()}"


def _policy_digests() -> dict[str, str]:
    return {
        "ctower.trust-spine-four-stage.execution@1": _file_digest(
            "packs/policies/execution/trust-spine-four-stage-v1.yaml"
        ),
        "ctower.trust-spine-four-stage.gates@1": _file_digest(
            "packs/policies/gates/trust-spine-four-stage-v1.yaml"
        ),
        "ctower.trust-spine-four-stage.evidence@1": _file_digest(
            "packs/policies/evidence/trust-spine-four-stage-v1.yaml"
        ),
    }


def _ticket(tenant: TenantFixture) -> UUID:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P2",
            project_key="ctower",
            source=SourceReference("test", f"test:workflow-start:{uuid4()}"),
            title="Explicit Workflow start",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    return outcome.ticket.ticket_id


def _telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )
