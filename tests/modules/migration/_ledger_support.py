"""Shared ledger-state helpers for the adoption and advance migration suites."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from ctower_kernel.record import _migration_ledger_sql, _setup_sql
from ctower_kernel.record.postgres import (
    MigrationBaseline,
    MigrationScript,
    apply_migrations,
    provision_database_roles,
)

from ._postgres import Database

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "packages/ctower-kernel/migrations/manifest.json"
# The ledger position the operator's own instance held when its v0.6.0 upgrade
# failed. Stopping a disposable database here reproduces that pending set.
LEDGERED_TERMINAL = "0035_board_source_lookup.sql"


def reset_to_empty_public_schema(database: Database) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public AUTHORIZATION pg_database_owner")
        connection.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
        connection.execute("COMMENT ON SCHEMA public IS 'standard public schema'")
    provision_database_roles(database.admin_dsn)


def ledger_rows(database: Database) -> list[tuple[object, ...]]:
    with psycopg.connect(database.admin_dsn) as connection:
        return connection.execute(
            """
            SELECT migration_id, sha256, application_kind, applied_at
            FROM ctower_schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()


def database_migration_ids() -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        entry["path"]
        for entry in manifest["migrations"]
        if entry.get("scope", "database") == "database"
    ]


def adoption_baseline_through() -> str:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return str(manifest["adoption_baseline"]["through"])


def use_migrations(
    monkeypatch: pytest.MonkeyPatch,
    scripts: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> None:
    loaded = _setup_sql._LoadedMigrations(scripts, baseline)
    monkeypatch.setattr(_setup_sql, "_load_migrations", lambda: loaded)


def install_ledger_through(
    database: Database,
    through: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leave one ledgered database stopped mid-history, as a served instance is.

    Cluster roles are provisioned from the complete manifest first, exactly as a
    released bootstrap does, so only the authored database history is truncated.
    """

    reset_to_empty_public_schema(database)
    loaded = _setup_sql._load_migrations()
    stop = next(
        position for position, script in enumerate(loaded.scripts) if script.migration_id == through
    )
    with monkeypatch.context() as truncated:
        use_migrations(truncated, loaded.scripts[: stop + 1], loaded.baseline)
        apply_migrations(database.migrator_dsn, role_admin_dsn=database.admin_dsn)


def record_used_instance_history(database: Database) -> tuple[list[tuple[object, ...]], ...]:
    """Write the history any served instance holds, including an underivable link.

    A catalog event carries a `catalog` subject link, which append_event writes
    on every published component and which the 0008 backfill query has no case
    for. That divergence is what rejected the operator's instance.
    """

    now = datetime.now(UTC)
    ticket_id, created_event, catalog_event = uuid4(), uuid4(), uuid4()
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            "INSERT INTO tenants (tenant_id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
            (database.tenant_id, "ctower", "Ctower", now),
        )
        connection.cursor().executemany(
            """
            INSERT INTO principals (
                principal_id, tenant_id, kind, display_name, disabled, created_at
            ) VALUES (%s, %s, %s, %s, false, %s)
            """,
            (
                (database.operator_id, database.tenant_id, "operator", "Migration Operator", now),
                (database.commander_id, database.tenant_id, "commander", "Ctower Commander", now),
            ),
        )
        connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, tenant_id, title, source_kind, source_ref, priority,
                custodian_principal_id, version, durability_state, created_by, created_at
            ) VALUES (%s, %s, 'Served history', 'test', 'history', 'P2', %s, 1,
                      'durability_pending', %s, %s)
            """,
            (ticket_id, database.tenant_id, database.operator_id, database.operator_id, now),
        )
        _insert_history_event(
            connection,
            database,
            event_id=created_event,
            kind="ticket.created",
            aggregate_id=ticket_id,
            record_position=1,
            now=now,
        )
        _insert_history_event(
            connection,
            database,
            event_id=catalog_event,
            kind="catalog.component_published",
            aggregate_id=database.tenant_id,
            record_position=2,
            now=now,
        )
        connection.cursor().executemany(
            """
            INSERT INTO event_links (event_id, tenant_id, subject_kind, subject_id)
            VALUES (%s, %s, %s, %s)
            """,
            (
                (created_event, database.tenant_id, "ticket", ticket_id),
                (catalog_event, database.tenant_id, "catalog", database.tenant_id),
            ),
        )
        connection.execute("UPDATE record_position_ledger SET last_position = 2 WHERE singleton")
    return history_rows(database)


def _insert_history_event(
    connection: psycopg.Connection[tuple[object, ...]],
    database: Database,
    *,
    event_id: UUID,
    kind: str,
    aggregate_id: UUID,
    record_position: int,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind, schema_version,
            actor_principal_id, client_command_id, request_sha256, correlation_id,
            causation_id, origin, server_time, payload, prev_hash, event_hash,
            record_position
        ) VALUES (
            %s, %s, %s, %s, 1, %s, 1, %s, %s, %s, %s, NULL, 'api', %s,
            '{}'::jsonb, %s, %s, %s
        )
        """,
        (
            event_id,
            database.tenant_id,
            f"{kind}:{aggregate_id}",
            aggregate_id,
            kind,
            database.operator_id,
            uuid4(),
            bytes(32),
            uuid4(),
            now,
            bytes(32),
            bytes([record_position]) * 32,
            record_position,
        ),
    )


def history_rows(database: Database) -> tuple[list[tuple[object, ...]], ...]:
    with psycopg.connect(database.admin_dsn) as connection:
        return (
            connection.execute(
                "SELECT ticket_id, title, version FROM tickets ORDER BY ticket_id"
            ).fetchall(),
            connection.execute(
                "SELECT event_id, kind, record_position, event_hash FROM events "
                "ORDER BY record_position"
            ).fetchall(),
            connection.execute(
                "SELECT event_id, subject_kind, subject_id FROM event_links "
                "ORDER BY event_id, subject_kind, subject_id"
            ).fetchall(),
            connection.execute(
                "SELECT last_position FROM record_position_ledger WHERE singleton"
            ).fetchall(),
        )


def adoption_rejections(database: Database) -> tuple[str, ...]:
    with psycopg.connect(database.admin_dsn) as connection:
        return _migration_ledger_sql._semantic_rejections(
            connection,
            _setup_sql._load_migrations().baseline,
            _migration_ledger_sql._SEMANTIC_CHECKS,
        )


def schema_snapshot(database: Database) -> tuple[str, tuple[tuple[str, str, str], ...]]:
    """Return the canonical catalog serialization the ledger itself attests."""

    with psycopg.connect(database.admin_dsn) as connection:
        records = _migration_ledger_sql._schema_records(connection)
    return (_migration_ledger_sql._schema_fingerprint(records), records)
