"""Real PostgreSQL tests for the column statistics target in the fingerprint (gh#80).

`ALTER COLUMN ... SET STATISTICS` changes how a column is planned but was invisible to the
canonical adoption fingerprint, which read `attribute.attstattarget` nowhere. An operator who
tuned planner statistics on a live column had that drift sit outside the recorded state.

Recording a new field on every 'column' record changes the digest of every already-ledgered
instance, exactly as the raw-vs-canonical rendering change from gh#247 did. This file proves the
same shape of fix: a ledger row recorded before this change still verifies, a real drift still
refuses, and the measurement does not confuse the persisted target with statistics ANALYZE
computes and stores separately in `pg_statistic`.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg import sql

from ctower_kernel.record import _migration_ledger_sql
from ctower_kernel.record.postgres import apply_migrations

from ._ledger_support import (
    LEDGERED_TERMINAL,
    adoption_baseline_through,
    install_ledger_through,
    ledger_rows,
    record_used_instance_history,
    rewrite_terminal_attestation,
)
from ._postgres import Database

__all__: tuple[str, ...] = ()

PROBE_TABLE = "tenants"
PROBE_COLUMN = "slug"


def test_a_non_default_statistics_target_changes_the_column_fingerprint(
    migration_database: Database,
) -> None:
    default_fingerprint = _fingerprint(migration_database)

    _set_statistics_target(migration_database, 500)

    assert _fingerprint(migration_database) != default_fingerprint


def test_restoring_the_default_statistics_target_restores_the_fingerprint(
    migration_database: Database,
) -> None:
    default_fingerprint = _fingerprint(migration_database)
    _set_statistics_target(migration_database, 500)
    assert _fingerprint(migration_database) != default_fingerprint

    _set_statistics_target(migration_database, -1)

    assert _fingerprint(migration_database) == default_fingerprint


def test_analyze_does_not_change_the_column_fingerprint(
    migration_database: Database,
) -> None:
    """The near miss: ANALYZE recomputes `pg_statistic`, not the configured target.

    `pg_statistic` holds the histogram/frequency data ANALYZE gathers, refreshed continuously by
    autovacuum. The fingerprint reads only `pg_attribute.attstattarget`, the persisted planner
    configuration, so ordinary database activity must never look like schema drift.
    """

    before = _fingerprint(migration_database)

    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute(sql.SQL("ANALYZE {}").format(sql.Identifier(PROBE_TABLE)))

    assert _fingerprint(migration_database) == before


def test_an_attestation_recorded_before_statistics_target_still_verifies(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every instance ledgered before gh#80 holds a digest without the field.

    It must still verify.
    """

    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    record_used_instance_history(migration_database)
    pre_statistics_target, current = _attestations(migration_database)
    assert pre_statistics_target != current
    rewrite_terminal_attestation(migration_database, pre_statistics_target)

    apply_migrations(
        migration_database.migrator_dsn,
        role_admin_dsn=migration_database.admin_dsn,
    )

    recorded = ledger_rows(migration_database)
    assert recorded[-1][0] == adoption_baseline_through()


def test_a_statistics_target_drift_still_fails_attestation(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tolerating the pre-gh#80 shape must not tolerate an actual statistics-target change."""

    install_ledger_through(migration_database, LEDGERED_TERMINAL, monkeypatch)
    record_used_instance_history(migration_database)
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute(
            sql.SQL("ALTER TABLE {} ALTER COLUMN {} SET STATISTICS 500").format(
                sql.Identifier(PROBE_TABLE), sql.Identifier(PROBE_COLUMN)
            )
        )

    with pytest.raises(_migration_ledger_sql.MigrationStateError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "ledger-schema-mismatch"


def _fingerprint(database: Database) -> str:
    with psycopg.connect(database.admin_dsn) as connection:
        return _migration_ledger_sql._schema_fingerprint(
            _migration_ledger_sql._schema_records(connection)
        )


def _set_statistics_target(database: Database, target: int) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            sql.SQL("ALTER TABLE {} ALTER COLUMN {} SET STATISTICS {}").format(
                sql.Identifier(PROBE_TABLE), sql.Identifier(PROBE_COLUMN), sql.Literal(target)
            )
        )


def _attestations(database: Database) -> tuple[str, str]:
    """The pre-gh#80 (no statistics_target) and current fingerprints of the same live schema."""

    with psycopg.connect(database.admin_dsn) as connection:
        current_records = _migration_ledger_sql._schema_records(connection)
        pre_statistics_target = _migration_ledger_sql._schema_fingerprint(
            _migration_ledger_sql._pre_attstattarget_schema_records(
                connection, current_records, canonical=True
            )
        )
        current = _migration_ledger_sql._schema_fingerprint(current_records)
    return pre_statistics_target, current
