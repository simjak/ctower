"""Real PostgreSQL tests for migration ledger state."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import psycopg
import pytest

from ctower_kernel.record.postgres import (
    MigrationAdoptionError,
    MigrationBaseline,
    MigrationScript,
    MigrationStateError,
    apply_database_migrations,
    apply_migrations,
    provision_database_roles,
)

from ._postgres import Database

__all__: tuple[str, ...] = ()
ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "packages/ctower-kernel/migrations/manifest.json"


def test_fresh_empty_database_migrates_once_and_repeat_is_noop(
    migration_database: Database,
) -> None:
    _reset_to_empty_public_schema(migration_database)

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )
    first = _ledger_rows(migration_database)
    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    assert len(first) == _database_migration_count()
    assert all(row[2] == "applied" for row in first)
    assert _ledger_rows(migration_database) == first
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute("SELECT to_regclass('public.tenants')").fetchone() == ("tenants",)


def test_matching_preledger_database_is_adopted_and_repeat_is_noop(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )
    first = _ledger_rows(migration_database)
    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    assert len(first) == _database_migration_count()
    assert all(row[2] == "baseline" for row in first)
    assert _ledger_rows(migration_database) == first


def test_preledger_schema_mismatch_is_typed_refusal_without_ledger(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE IF EXISTS ctower_schema_migrations")
        connection.execute("ALTER TABLE tenants ADD COLUMN unreviewed_marker text")

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-schema-mismatch"
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.ctower_schema_migrations')"
        ).fetchone() == (None,)


def test_preledger_semantic_mismatch_is_typed_refusal_without_ledger(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE IF EXISTS ctower_schema_migrations")
        connection.execute("UPDATE record_position_ledger SET last_position = last_position + 1")

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-semantic-mismatch"
    assert "record-position-ledger" in raised.value.detail
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.ctower_schema_migrations')"
        ).fetchone() == (None,)


def test_existing_ledger_checksum_drift_is_typed_refusal(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE ctower_schema_migrations
            SET sha256 = %s
            WHERE migration_id = (
                SELECT min(migration_id) FROM ctower_schema_migrations
            )
            """,
            ("sha256:" + ("f" * 64),),
        )

    with pytest.raises(MigrationStateError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "ledger-checksum-mismatch"


def test_failed_migration_rolls_back_schema_and_ledger(
    migration_database: Database,
) -> None:
    _reset_to_empty_public_schema(migration_database)
    sha256 = "sha256:" + ("a" * 64)
    migrations = (
        MigrationScript(
            "9000_transaction_probe.sql",
            sha256,
            "database",
            "CREATE TABLE transaction_probe (marker integer)",
        ),
        MigrationScript(
            "9001_broken_probe.sql",
            sha256,
            "database",
            "CREATE TABLE broken_probe (",
        ),
    )
    baseline = MigrationBaseline(
        "9001_broken_probe.sql",
        "sha256:" + ("0" * 64),
        "ctower.pre-ledger/v1",
    )

    with (
        pytest.raises(psycopg.errors.SyntaxError),
        psycopg.connect(migration_database.migrator_dsn) as connection,
    ):
        connection.execute("SET ROLE ctower_admin")
        apply_database_migrations(connection, migrations, baseline)

    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            """
            SELECT to_regclass('public.transaction_probe'),
                   to_regclass('public.ctower_schema_migrations')
            """
        ).fetchone() == (None, None)


def test_two_concurrent_fresh_callers_apply_every_migration_once(
    migration_database: Database,
) -> None:
    _reset_to_empty_public_schema(migration_database)
    start = Barrier(2)

    def migrate() -> None:
        start.wait()
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = (workers.submit(migrate), workers.submit(migrate))
        for future in futures:
            future.result(timeout=60)

    rows = _ledger_rows(migration_database)
    assert len(rows) == _database_migration_count()
    assert len({row[0] for row in rows}) == len(rows)
    assert all(row[2] == "applied" for row in rows)


def _reset_to_empty_public_schema(database: Database) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public AUTHORIZATION pg_database_owner")
    provision_database_roles(database.admin_dsn)


def _ledger_rows(database: Database) -> list[tuple[object, ...]]:
    with psycopg.connect(database.admin_dsn) as connection:
        return connection.execute(
            """
            SELECT migration_id, sha256, application_kind, applied_at
            FROM ctower_schema_migrations
            ORDER BY migration_id
            """
        ).fetchall()


def _database_migration_count() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return sum(entry.get("scope", "database") == "database" for entry in manifest["migrations"])
