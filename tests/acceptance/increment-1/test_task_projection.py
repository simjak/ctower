"""Truthful Board watermark and disposable rebuild acceptance tracers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from support.tenant_fixture import TenantFixture

from ctower_kernel.projections import BoardLane, BoardQuery, ProjectionHealth, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Admit, ChangePriority, Defer, Work, WorkReceipt
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()


def test_defer_stays_backlog_until_explicit_admission(tenant: TenantFixture) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    ticket_id = _ticket(tenant)
    work = Work(
        PostgresRecord(tenant.database.runtime_dsn),
        writer=PostgresWork(tenant.database.runtime_dsn),
    )
    projections = Projections(PostgresProjections(tenant.database.admin_dsn))

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
    backlog = projections.catch_up(tenant.tenant_id)
    admitted = work.execute(
        actor,
        Admit(uuid4(), ticket_id, 2, "Capacity is available"),
        telemetry=_telemetry(),
    )
    ready = projections.catch_up(tenant.tenant_id)

    assert isinstance(deferred, WorkReceipt)
    assert isinstance(admitted, WorkReceipt)
    assert backlog.cards[0].lane is BoardLane.BACKLOG
    assert ready.cards[0].lane is BoardLane.READY


def test_board_watermarks_staleness_and_rebuild_equality(tenant: TenantFixture) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    ticket_id = _ticket(tenant)
    store = PostgresProjections(tenant.database.admin_dsn)
    projections = Projections(store)

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
    stale = projections.board(actor, BoardQuery())
    ready = projections.catch_up(tenant.tenant_id)
    rebuilt = projections.rebuild(tenant.tenant_id)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "DELETE FROM board_projection_rows WHERE tenant_id = %s AND ticket_id = %s",
            (tenant.tenant_id, ticket_id),
        )
    missing = projections.board(actor, BoardQuery())

    assert isinstance(admitted, WorkReceipt)
    assert backlog.health is ProjectionHealth.CURRENT
    assert backlog.cards[0].lane is BoardLane.BACKLOG
    assert stale.health is ProjectionHealth.STATE_UNKNOWN
    assert stale.source_watermark > stale.projection_watermark
    assert ready.health is ProjectionHealth.CURRENT
    assert ready.cards[0].lane is BoardLane.READY
    assert rebuilt.response_payload() == ready.response_payload()
    assert missing.health is ProjectionHealth.STATE_UNKNOWN


@pytest.mark.parametrize("fault", ("behind", "ahead", "gap", "unknown-event"))
def test_board_reports_loud_unknown_for_cursor_and_source_faults(
    tenant: TenantFixture, fault: str
) -> None:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    ticket_id = _ticket(tenant)
    projections = Projections(PostgresProjections(tenant.database.admin_dsn))
    current = projections.catch_up(tenant.tenant_id)
    assert current.health is ProjectionHealth.CURRENT

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        if fault == "ahead":
            connection.execute(
                "UPDATE projection_cursors SET projection_watermark = %s WHERE tenant_id = %s",
                (current.source_watermark + 1, tenant.tenant_id),
            )
        elif fault == "gap":
            connection.execute("SELECT nextval('events_record_position_seq')")
        else:
            connection.execute("ALTER TABLE events DROP CONSTRAINT events_kind_check")
            connection.execute(
                "UPDATE events SET kind = 'future.changed' WHERE record_position = %s",
                (current.source_watermark,),
            )

    if fault == "behind":
        unknown = projections.catch_up(tenant.tenant_id, current.source_watermark - 1)
    elif fault == "gap":
        committed = Work(
            PostgresRecord(tenant.database.runtime_dsn),
            writer=PostgresWork(tenant.database.runtime_dsn),
        ).execute(
            actor,
            ChangePriority(uuid4(), ticket_id, 1, "Gap fault command", "P1"),
            telemetry=_telemetry(),
        )
        assert isinstance(committed, WorkReceipt)
        unknown = projections.catch_up(tenant.tenant_id)
    else:
        unknown = projections.catch_up(tenant.tenant_id)

    assert unknown.health is ProjectionHealth.STATE_UNKNOWN
    assert unknown.source_watermark != unknown.projection_watermark or fault in {
        "behind",
        "unknown-event",
    }


def _ticket(tenant: TenantFixture) -> UUID:
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        actor,
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P2",
            source=SourceReference("test", f"test:board-projection:{uuid4()}"),
            title="Board projection health",
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
