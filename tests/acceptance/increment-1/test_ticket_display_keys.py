"""Disposable PostgreSQL evidence for Ticket display-key capture and lookup."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from support.acceptance import accept_pending_commands
from support.catalog import (
    FileSchemas,
    MemoryObjectStore,
    actor_for,
    apply_initial_bundle,
    minimal_bundle,
    telemetry_for,
)
from support.postgres import DatabaseFixture
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.catalog import PostgresCatalog
from ctower_kernel.catalog.interface import CompanyBundle
from ctower_kernel.projections import BoardQuery, Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    SourceReference,
    TicketCommand,
    TicketCommandResult,
    _migration_ledger_sql,
    _setup_sql,
)
from ctower_kernel.record.postgres import PostgresRecord, apply_migrations, provision_database_roles
from ctower_kernel.work import Work

__all__: tuple[str, ...] = ()
HTTP_OK = 200


def test_fresh_apply_creates_display_key_authority_objects(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        sequence = connection.execute(
            """
            SELECT to_regclass('public.ticket_display_sequences'),
                to_regclass('public.tickets_display_key'),
                to_regclass('public.board_projection_display_key')
            """
        ).fetchone()
        trigger = connection.execute(
            """
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'tickets_display_key_immutable'
            """
        ).fetchone()
        columns = connection.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name IN ('tickets', 'board_projection_rows')
              AND column_name = 'display_key'
            ORDER BY table_name
            """
        ).fetchall()

    assert sequence == (
        "ticket_display_sequences",
        "tickets_display_key",
        "board_projection_display_key",
    )
    assert trigger == (1,)
    assert [row[0] for row in columns] == ["display_key", "display_key"]


def test_backfill_orders_preexisting_rows_and_advances_the_project_sequence(
    database: DatabaseFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provision_database_roles(database.admin_dsn)
    loaded = _setup_sql._load_migrations()
    stop = next(
        index
        for index, script in enumerate(loaded.scripts)
        if script.migration_id == "0074_restore_routine_retirement_kind.sql"
    )
    with monkeypatch.context() as truncated:
        truncated.setattr(
            _setup_sql,
            "_load_migrations",
            lambda: _setup_sql._LoadedMigrations(loaded.scripts[: stop + 1], loaded.baseline),
        )
        apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)

    tenant_id, operator_id, commander_id = uuid4(), uuid4(), uuid4()
    first_id, second_id = uuid4(), uuid4()
    older = datetime(2026, 8, 1, tzinfo=UTC)
    newer = datetime(2026, 8, 2, tzinfo=UTC)
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            """
            ALTER TABLE catalog_component_revisions
                ADD COLUMN project_prefix text CHECK (
                    project_prefix IS NULL OR project_prefix ~ '^[A-Z]{2,5}$'
                )
            """
        )
        connection.execute(
            """
            INSERT INTO tenants (tenant_id, slug, name, created_at)
            VALUES (%s, 'ctower', 'Ctower', %s)
            """,
            (tenant_id, older),
        )
        connection.cursor().executemany(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, %s, %s, false, %s)
            """,
            (
                (operator_id, tenant_id, "operator", "Migration operator", older),
                (commander_id, tenant_id, "commander", "Migration commander", older),
            ),
        )
        connection.execute(
            """
            INSERT INTO project_seats (
                principal_id, tenant_id, project_key, seat_key, granted_by, granted_at
            ) VALUES (%s, %s, 'ctower', 'ctower-commander', %s, %s)
            """,
            (commander_id, tenant_id, operator_id, older),
        )
        connection.cursor().executemany(
            """
            INSERT INTO tickets (
                ticket_id, tenant_id, title, source_kind, source_ref, priority,
                custodian_principal_id, version, durability_state, created_by, created_at,
                project_key
            ) VALUES (%s, %s, %s, 'test', %s, 'P1', %s, 1, 'durability_pending', %s, %s, 'ctower')
            """,
            (
                (first_id, tenant_id, "Older", "backfill:older", commander_id, operator_id, older),
                (second_id, tenant_id, "Newer", "backfill:newer", commander_id, operator_id, newer),
            ),
        )

    actor = Actor(operator_id, tenant_id, PrincipalKind.OPERATOR)
    catalog = PostgresCatalog(
        database.runtime_dsn,
        FileSchemas(),
        MemoryObjectStore(),
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 8, 17, tzinfo=UTC),
    )
    apply_initial_bundle(catalog, actor, minimal_bundle())
    with monkeypatch.context() as migration_step:
        migration_step.setattr(_migration_ledger_sql, "_recorded_state_matches", lambda *_: None)
        apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)

    with psycopg.connect(database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT ticket_id, display_key FROM tickets
            WHERE tenant_id = %s ORDER BY created_at, ticket_id
            """,
            (tenant_id,),
        ).fetchall()
        sequence = connection.execute(
            """
            SELECT next_number FROM ticket_display_sequences
            WHERE tenant_id = %s AND project_key = 'ctower'
            """,
            (tenant_id,),
        ).fetchone()

    assert rows == [(first_id, "CTW-1"), (second_id, "CTW-2")]
    assert sequence == (3,)


def test_capture_replay_lookup_and_immutable_gap_are_project_scoped(
    tenant: TenantFixture,
) -> None:
    _apply_prefix_bundle(tenant)
    actor = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    record = PostgresRecord(tenant.database.runtime_dsn)
    work = Work(record)
    first_command = _command(tenant, "first")

    first = work.create_ticket(
        actor, first_command, telemetry=telemetry_for(actor, first_command.client_command_id)
    )
    assert isinstance(first, TicketCommandResult)
    assert first.ticket.display_key == "CTW-1"
    replay = work.create_ticket(
        actor, first_command, telemetry=telemetry_for(actor, first_command.client_command_id)
    )
    assert isinstance(replay, TicketCommandResult)
    assert replay == first

    second_command = _command(tenant, "second")
    second = work.create_ticket(
        actor, second_command, telemetry=telemetry_for(actor, second_command.client_command_id)
    )
    assert isinstance(second, TicketCommandResult)
    assert second.ticket.display_key == "CTW-2"
    assert second.ticket.ticket_id != first.ticket.ticket_id

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        with pytest.raises(psycopg.Error) as raised:
            connection.execute(
                "UPDATE tickets SET display_key = 'CTW-99' WHERE tenant_id = %s AND ticket_id = %s",
                (tenant.tenant_id, first.ticket.ticket_id),
            )
        assert raised.value.sqlstate == "55000"
        connection.rollback()
        connection.execute(
            """
            UPDATE ticket_display_sequences SET next_number = 5
            WHERE tenant_id = %s AND project_key = 'ctower'
            """,
            (tenant.tenant_id,),
        )

    third_command = _command(tenant, "after-gap")
    third = work.create_ticket(
        actor, third_command, telemetry=telemetry_for(actor, third_command.client_command_id)
    )
    assert isinstance(third, TicketCommandResult)
    assert third.ticket.display_key == "CTW-5"

    accept_pending_commands(tenant.database.admin_dsn, tenant.tenant_id)
    board = Projections(PostgresProjections(tenant.database.projection_dsn))
    board.catch_up(tenant.tenant_id)
    view = board.board(
        actor_for(tenant.tenant_id, tenant.operator_id), BoardQuery(project_key="ctower")
    )
    assert {card.display_key for card in view.cards} >= {"CTW-1", "CTW-2", "CTW-5"}

    with TestClient(
        create_app(record, work=work),
        client=("127.0.0.1", 51000),
    ) as client:
        response = client.get(
            "/v1/tickets/CTW-1",
            params={"project_key": "ctower"},
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                **telemetry_headers(),
            },
        )
    assert response.status_code == HTTP_OK
    assert response.json()["ticket_id"] == str(first.ticket.ticket_id)
    assert response.json()["display_key"] == "CTW-1"


def _apply_prefix_bundle(tenant: TenantFixture) -> None:
    actor = actor_for(tenant.tenant_id, tenant.operator_id)
    store = MemoryObjectStore()
    catalog = PostgresCatalog(
        tenant.database.runtime_dsn,
        FileSchemas(),
        store,
        key_reference="vault:catalog-key",
        clock=lambda: datetime(2026, 8, 17, tzinfo=UTC),
    )
    apply_initial_bundle(catalog, actor, _bundle_with_project_prefix())


def _bundle_with_project_prefix() -> CompanyBundle:
    return minimal_bundle()


def _command(tenant: TenantFixture, suffix: str) -> TicketCommand:
    return TicketCommand(
        client_command_id=uuid4(),
        initial_custodian_id=tenant.commander_id,
        priority="P1",
        project_key="ctower",
        source=SourceReference("test", "display-key:" + suffix),
        title="display-key " + suffix,
    )
