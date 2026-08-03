"""Real PostgreSQL tests for advancing an already-ledgered database (gh#232)."""

from __future__ import annotations

import psycopg
import pytest

from ctower_kernel.record import _setup_sql
from ctower_kernel.record.postgres import (
    MigrationPreconditionError,
    MigrationScript,
    MigrationStateError,
    apply_migrations,
)

from ._ledger_support import (
    LEDGERED_TERMINAL,
    adoption_baseline_through,
    adoption_rejections,
    database_migration_ids,
    history_rows,
    install_ledger_through,
    ledger_rows,
    record_used_instance_history,
    reset_to_empty_public_schema,
    schema_snapshot,
    use_migrations,
)
from ._postgres import Database

__all__: tuple[str, ...] = ()


def test_ledgered_database_with_history_completes_the_full_pending_set(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    history = record_used_instance_history(migration_database)
    recorded_before = ledger_rows(migration_database)
    # The adoption question this database cannot answer, and never has to: it
    # holds history, and it holds a link 0008's backfill query cannot derive.
    assert adoption_rejections(migration_database) == (
        "record-position-history-unprovable",
        "event-link-backfill",
    )

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    recorded_after = ledger_rows(migration_database)
    identifiers = database_migration_ids()
    assert [row[0] for row in recorded_before] == identifiers[: len(recorded_before)]
    assert [row[0] for row in recorded_after] == identifiers
    assert recorded_after[-1][0] == adoption_baseline_through()
    assert all(row[2] == "applied" for row in recorded_after)
    assert history_rows(migration_database) == history
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute("SELECT to_regclass('public.project_seats')").fetchone() == (
            "project_seats",
        )


def test_failing_advance_precondition_leaves_the_schema_and_ledger_untouched(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    record_used_instance_history(migration_database)
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("UPDATE record_position_ledger SET last_position = last_position + 1")
    schema_before = schema_snapshot(migration_database)
    recorded_before = ledger_rows(migration_database)

    with pytest.raises(MigrationPreconditionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "advance-precondition-mismatch"
    assert raised.value.detail == "record-position-ledger"
    assert schema_snapshot(migration_database) == schema_before
    assert ledger_rows(migration_database) == recorded_before
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute("SELECT to_regclass('public.project_seats')").fetchone() == (
            None,
        )


def test_executed_invariant_failure_rolls_back_before_the_schema_commits(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_to_empty_public_schema(migration_database)
    loaded = _setup_sql._load_migrations()
    breaking = MigrationScript(
        "9999_invariant_probe.sql",
        "sha256:" + ("c" * 64),
        "database",
        "UPDATE record_position_ledger SET last_position = last_position + 5",
    )
    use_migrations(monkeypatch, (*loaded.scripts, breaking), loaded.baseline)

    with pytest.raises(MigrationStateError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "ledger-semantic-mismatch"
    assert raised.value.detail == "record-position-ledger"
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            """
            SELECT to_regclass('public.tenants'),
                   to_regclass('public.ctower_schema_migrations')
            """
        ).fetchone() == (None, None)
