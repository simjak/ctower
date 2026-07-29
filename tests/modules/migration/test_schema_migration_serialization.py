"""Migration control-lock coverage of cluster-global role reconciliation."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import psycopg

from ctower_kernel.record.postgres import apply_migrations

from ._postgres import Database

_MIGRATION_CONTROL_LOCK = 712040119


def test_migration_lock_precedes_cluster_role_reconciliation(
    migration_database: Database,
) -> None:
    with (
        psycopg.connect(migration_database.admin_dsn, autocommit=True) as barrier,
        psycopg.connect(migration_database.projection_dsn, autocommit=True) as active_projection,
    ):
        barrier.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_CONTROL_LOCK,))
        with ThreadPoolExecutor(max_workers=1) as worker:
            migration = worker.submit(
                apply_migrations,
                migration_database.migrator_dsn,
                role_admin_dsn=migration_database.admin_dsn,
            )
            try:
                _wait_for_migration_lock(migration_database)
                assert active_projection.execute("SELECT 1").fetchone() == (1,)
            finally:
                active_projection.close()
                barrier.execute(
                    "SELECT pg_advisory_unlock(%s)",
                    (_MIGRATION_CONTROL_LOCK,),
                )
            migration.result(timeout=60)


def _wait_for_migration_lock(database: Database) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with psycopg.connect(database.admin_dsn) as connection:
            waiting = connection.execute(
                """
                SELECT 1 FROM pg_stat_activity
                WHERE datname = current_database()
                  AND wait_event_type = 'Lock'
                  AND wait_event = 'advisory'
                  AND query LIKE 'SELECT pg_advisory_lock%'
                """
            ).fetchone()
        if waiting is not None:
            return
        time.sleep(0.02)
    raise AssertionError("migration caller did not wait for the control lock")
