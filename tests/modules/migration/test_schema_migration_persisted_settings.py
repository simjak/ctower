"""Persisted PostgreSQL-setting coverage for pre-ledger schema adoption."""

from __future__ import annotations

from typing import Literal

import psycopg
import pytest
from psycopg import sql

from ctower_kernel.record.postgres import MigrationAdoptionError, apply_migrations

from ._postgres import Database

__all__: tuple[str, ...] = ()

type _SettingScope = Literal["database", "role", "database-role"]


@pytest.mark.parametrize(
    ("scope", "name", "value"),
    (
        ("database", "session_replication_role", "replica"),
        ("role", "default_transaction_read_only", "on"),
        ("database-role", "default_transaction_isolation", "serializable"),
        ("role", "synchronous_commit", "off"),
    ),
    ids=(
        "database-session-replication-role",
        "role-default-transaction-read-only",
        "database-role-default-transaction-isolation",
        "role-synchronous-commit",
    ),
)
def test_persisted_database_and_runtime_role_settings_are_typed_refusals(
    migration_database: Database,
    scope: _SettingScope,
    name: str,
    value: str,
) -> None:
    database_name = _current_database_name(migration_database)
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
    _persist_setting(
        migration_database,
        database_name=database_name,
        scope=scope,
        name=name,
        value=value,
    )

    with pytest.raises(MigrationAdoptionError) as raised:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )

    assert raised.value.code == "baseline-configuration-mismatch"
    assert name in raised.value.detail
    assert scope in raised.value.detail
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.ctower_schema_migrations')"
        ).fetchone() == (None,)


def _current_database_name(database: Database) -> str:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute("SELECT current_database()").fetchone()
    if row is None:
        raise RuntimeError("current database is unavailable")
    return str(row[0])


def _persist_setting(
    database: Database,
    *,
    database_name: str,
    scope: _SettingScope,
    name: str,
    value: str,
) -> None:
    role = sql.Identifier("ctower_runtime")
    setting = sql.Identifier(name)
    setting_value = sql.Literal(value)
    if scope == "database":
        statement = sql.SQL("ALTER DATABASE {} SET {} = {}").format(
            sql.Identifier(database_name),
            setting,
            setting_value,
        )
    elif scope == "role":
        statement = sql.SQL("ALTER ROLE {} SET {} = {}").format(
            role,
            setting,
            setting_value,
        )
    else:
        statement = sql.SQL("ALTER ROLE {} IN DATABASE {} SET {} = {}").format(
            role,
            sql.Identifier(database_name),
            setting,
            setting_value,
        )
    with psycopg.connect(database.admin_dsn, autocommit=True) as connection:
        connection.execute(statement)
