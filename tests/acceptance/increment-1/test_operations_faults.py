"""PostgreSQL restart recovery for CP3-B projection fold failures."""

from __future__ import annotations

from uuid import uuid4

import psycopg
from support.acceptance import accept_command
from support.tenant_fixture import TenantFixture

from ctower_kernel.projections import ProjectionHealth, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem, SourceReference, TicketCommand
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import Work


def test_projection_restart_replays_retryable_fold_without_partial_cursor(
    tenant: TenantFixture,
) -> None:
    outcome = Work(PostgresRecord(tenant.database.runtime_dsn)).create_ticket(
        Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER),
        TicketCommand(
            client_command_id=uuid4(),
            initial_custodian_id=tenant.commander_id,
            priority="P1",
            source=SourceReference("test", "test:projection-restart"),
            title="Projection restart recovery",
        ),
        telemetry=_telemetry(),
    )
    assert not isinstance(outcome, RecordProblem)
    accept_command(
        tenant.database.admin_dsn,
        tenant.tenant_id,
        tenant.commander_id,
        outcome.command_id,
    )
    _install_one_fold_failure(tenant)

    failed = Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(
        tenant.tenant_id
    )
    _remove_fold_failure(tenant)
    restarted = Projections(PostgresProjections(tenant.database.projection_dsn)).catch_up(
        tenant.tenant_id
    )

    assert failed.cards == ()
    assert failed.projection_watermark == 0
    assert restarted.health is ProjectionHealth.CURRENT
    assert [card.ticket_id for card in restarted.cards] == [outcome.ticket.ticket_id]
    assert _attempt_outcomes(tenant) == ("retryable_failure", "delivered")


def _install_one_fold_failure(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            CREATE FUNCTION ctower_test_restart_fold_failure() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'restart fold failure'; END $$;
            CREATE TRIGGER ctower_test_restart_fold_failure
            BEFORE INSERT ON board_projection_rows FOR EACH ROW
            EXECUTE FUNCTION ctower_test_restart_fold_failure();
            """
        )


def _remove_fold_failure(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute("DROP TRIGGER ctower_test_restart_fold_failure ON board_projection_rows")
        connection.execute("DROP FUNCTION ctower_test_restart_fold_failure()")


def _attempt_outcomes(tenant: TenantFixture) -> tuple[str, ...]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            "SELECT outcome FROM outbox_delivery_attempts ORDER BY recorded_at, attempt_number"
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


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
