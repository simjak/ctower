"""Constraint-trigger coverage for pre-ledger schema adoption."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import psycopg

from ctower_kernel.record.postgres import MigrationAdoptionError, apply_migrations

from ._postgres import Database

__all__: tuple[str, ...] = ()


def test_disabled_internal_constraint_triggers_are_refused_without_names_or_oids(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        connection.execute("DROP TABLE ctower_schema_migrations")
        connection.execute("ALTER TABLE principals DISABLE TRIGGER ALL")
    assert _internal_constraint_triggers_disabled(migration_database)

    outcome = "REFUSED"
    try:
        apply_migrations(
            migration_database.migrator_dsn,
            role_admin_dsn=migration_database.admin_dsn,
        )
    except MigrationAdoptionError as error:
        assert error.code == "baseline-schema-mismatch"
    else:
        with psycopg.connect(migration_database.admin_dsn) as connection:
            connection.execute(
                """
                INSERT INTO principals (
                    principal_id, tenant_id, kind, display_name, disabled, created_at
                ) VALUES (%s, %s, 'operator', 'Foreign-key probe', false, %s)
                """,
                (uuid4(), uuid4(), datetime.now(UTC)),
            )
        outcome = "ACCEPTED_WITHOUT_PARENT"

    assert outcome == "REFUSED", f"fk_probe={outcome}"
    with psycopg.connect(migration_database.admin_dsn) as connection:
        assert connection.execute(
            "SELECT to_regclass('public.ctower_schema_migrations')"
        ).fetchone() == (None,)
    assert _internal_constraint_triggers_disabled(migration_database)


def _internal_constraint_triggers_disabled(database: Database) -> bool:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT count(*) > 0 AND bool_and(trigger.tgenabled = 'D')
            FROM pg_trigger AS trigger
            JOIN pg_class AS class ON class.oid = trigger.tgrelid
            JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
            WHERE namespace.nspname = 'public'
              AND class.relname = 'principals'
              AND trigger.tgisinternal
              AND trigger.tgconstraint <> 0
            """
        ).fetchone()
    return row == (True,)
