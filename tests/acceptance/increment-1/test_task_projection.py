"""Truthful Board watermark and disposable rebuild acceptance tracers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from support.acceptance import accept_pending_commands
from support.projection_faults import (
    InjectedOutboxFailure,
    ProjectionFault,
    ProjectionFaults,
)
from support.tenant_fixture import TenantFixture

from ctower_kernel.projections import (
    BoardLane,
    BoardQuery,
    BoardView,
    ProjectionHealth,
    Projections,
)
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Admit, ChangePriority, Defer, Work, WorkReceipt
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()


def test_defer_stays_backlog_until_explicit_admission(tenant: TenantFixture) -> None:
    actor = Actor(
        tenant.commander_id,
        tenant.tenant_id,
        PrincipalKind.COMMANDER,
        project_grants=frozenset({"ctower"}),
    )
    ticket_id = _ticket(tenant)
    work = Work(
        PostgresRecord(tenant.database.runtime_dsn),
        writer=PostgresWork(tenant.database.runtime_dsn),
    )
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)

    deferred = work.execute(
        actor,
        Defer(
            uuid4(),
            ticket_id,
            1,
            "Wait for the capacity review",
            datetime.now(UTC) + timedelta(days=1),
        ),
        telemetry=_telemetry(),
    )
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    projections.catch_up(tenant.tenant_id)
    backlog_board = _board(projections, actor, "ctower")
    admitted = work.execute(
        actor,
        Admit(uuid4(), ticket_id, 2, "Capacity is available"),
        telemetry=_telemetry(),
    )
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    ready = projections.catch_up(tenant.tenant_id)

    assert isinstance(deferred, WorkReceipt)
    assert isinstance(admitted, WorkReceipt)
    assert backlog_board.cards[0].lane is BoardLane.BACKLOG
    assert ready.health is ProjectionHealth.CURRENT
    assert _board(projections, actor, "ctower").cards[0].lane is BoardLane.READY


def test_board_watermarks_staleness_and_rebuild_equality(tenant: TenantFixture) -> None:
    actor = Actor(
        tenant.commander_id,
        tenant.tenant_id,
        PrincipalKind.COMMANDER,
        project_grants=frozenset({"ctower"}),
    )
    ticket_id = _ticket(tenant)
    store = PostgresProjections(tenant.database.projection_dsn)
    projections = Projections(store)

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    backlog = projections.catch_up(tenant.tenant_id)
    work = Work(
        PostgresRecord(tenant.database.runtime_dsn),
        writer=PostgresWork(tenant.database.runtime_dsn),
    )
    admitted = work.execute(
        actor,
        Admit(uuid4(), ticket_id, 1, "Admit to ready queue"),
        telemetry=_telemetry(),
    )
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    stale = projections.board(actor, BoardQuery(project_key="ctower"))
    assert not isinstance(stale, RecordProblem), stale
    ready = projections.catch_up(tenant.tenant_id)
    ready_board = _board(projections, actor, "ctower")
    rebuilt = projections.rebuild(tenant.tenant_id)
    rebuilt_board = _board(projections, actor, "ctower")
    ProjectionFaults(tenant.database.admin_dsn).remove_projected_card(tenant.tenant_id, ticket_id)
    missing = projections.board(actor, BoardQuery(project_key="ctower"))
    assert not isinstance(missing, RecordProblem), missing

    assert isinstance(admitted, WorkReceipt)
    assert backlog.health is ProjectionHealth.CURRENT
    assert stale.health is ProjectionHealth.STATE_UNKNOWN
    assert stale.source_watermark > stale.projection_watermark
    assert ready.health is ProjectionHealth.CURRENT
    assert ready_board.cards[0].lane is BoardLane.READY
    assert rebuilt.health is ready.health
    assert rebuilt.source_watermark == ready.source_watermark
    assert rebuilt.projection_watermark == ready.projection_watermark
    assert rebuilt_board.response_payload() == ready_board.response_payload()
    assert missing.health is ProjectionHealth.STATE_UNKNOWN


def test_rebuild_equality_turns_red_when_the_rebuild_corrupts_a_card(
    tenant: TenantFixture,
) -> None:
    """The pre/post oracle the three rebuild tests use must see rebuild-time drift."""

    actor = Actor(
        tenant.commander_id,
        tenant.tenant_id,
        PrincipalKind.COMMANDER,
        project_grants=frozenset({"ctower"}),
    )
    _ticket(tenant)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    caught_up = projections.catch_up(tenant.tenant_id)
    accepted_board = _board(projections, actor, "ctower")

    with ProjectionFaults(tenant.database.admin_dsn).corrupt_projected_priority("P0"):
        rebuilt = projections.rebuild(tenant.tenant_id)
    rebuilt_board = _board(projections, actor, "ctower")

    assert accepted_board.cards[0].priority == "P2"
    assert rebuilt_board.cards[0].priority == "P0"
    assert rebuilt.health is caught_up.health
    assert rebuilt.source_watermark == caught_up.source_watermark
    assert rebuilt.projection_watermark == caught_up.projection_watermark
    assert rebuilt_board.response_payload() != accepted_board.response_payload()


def test_rolled_back_outbox_append_retries_without_poisoning_board(
    tenant: TenantFixture,
) -> None:
    actor = Actor(
        tenant.commander_id,
        tenant.tenant_id,
        PrincipalKind.COMMANDER,
        project_grants=frozenset({"ctower"}),
    )
    ticket_id = _ticket(tenant)
    work = Work(
        PostgresRecord(tenant.database.runtime_dsn),
        writer=PostgresWork(tenant.database.runtime_dsn),
    )
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    before = projections.catch_up(tenant.tenant_id)
    command = ChangePriority(uuid4(), ticket_id, 1, "Rollback-safe priority", "P1")

    faults = ProjectionFaults(tenant.database.admin_dsn)
    with faults.reject_outbox_appends(), pytest.raises(InjectedOutboxFailure):
        work.execute(actor, command, telemetry=_telemetry())

    retried = work.execute(actor, command, telemetry=_telemetry())
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    caught_up = projections.catch_up(tenant.tenant_id)
    caught_up_board = _board(projections, actor, "ctower")
    rebuilt = projections.rebuild(tenant.tenant_id)
    rebuilt_board = _board(projections, actor, "ctower")
    positions = faults.record_positions()

    assert isinstance(retried, WorkReceipt)
    assert positions == tuple(range(1, len(positions) + 1))
    assert caught_up.health is ProjectionHealth.CURRENT
    assert caught_up.source_watermark == before.source_watermark + 1
    assert rebuilt.health is caught_up.health
    assert rebuilt.source_watermark == caught_up.source_watermark
    assert rebuilt.projection_watermark == caught_up.projection_watermark
    assert caught_up_board.cards
    assert rebuilt_board.response_payload() == caught_up_board.response_payload()


@pytest.mark.parametrize("fault", ("behind", "ahead"))
def test_board_reports_loud_unknown_for_cursor_and_source_faults(
    tenant: TenantFixture, fault: ProjectionFault
) -> None:
    _ticket(tenant)
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    current = projections.catch_up(tenant.tenant_id)
    assert current.health is ProjectionHealth.CURRENT

    ProjectionFaults(tenant.database.admin_dsn).inject_source_fault(
        tenant.tenant_id, current.source_watermark, fault
    )

    if fault == "behind":
        unknown = projections.catch_up(tenant.tenant_id, current.source_watermark - 1)
    else:
        unknown = projections.catch_up(tenant.tenant_id)

    assert unknown.health is ProjectionHealth.STATE_UNKNOWN
    assert unknown.source_watermark != unknown.projection_watermark or fault == "behind"


def _ticket(tenant: TenantFixture) -> UUID:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P2",
            project_key="ctower",
            source=SourceReference("test", f"test:board-projection:{uuid4()}"),
            title="Board projection health",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    return outcome.ticket.ticket_id


def _board(projections: Projections, actor: Actor, project_key: str) -> BoardView:
    board = projections.board(actor, BoardQuery(project_key=project_key))
    assert not isinstance(board, RecordProblem), board
    return board


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
