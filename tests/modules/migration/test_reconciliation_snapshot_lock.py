"""Final reconciliation serializes every run-bound mutable target head."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from ctower_client.models import CtowerProjectImportRun, CtowerProjectReconciliationResult
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import ChangePriority, Work, WorkReceipt
from ctower_kernel.work.postgres import PostgresWork
from tools.migration.ctower_project.ctower_project_source.executor import (
    ImportPassReceipt,
    execute_import,
)

from . import test_postgres as spine
from ._checkpoint_truth import refresh_checkpoint_truth
from ._postgres import Database

_BARRIER_KEY = 8_174_004_002
_CHECKPOINT_COUNT = 14
__all__: tuple[str, ...] = ()


def test_finalize_holds_target_heads_until_reconciliation_commit(
    migration_database: Database,
    tmp_path: Path,
) -> None:
    context, ready = _ready_run(migration_database, tmp_path)
    ticket_id, version, priority = _bound_ticket(migration_database, ready.run_id)
    finalize_command = uuid4()
    work_command = uuid4()
    result, changed, rebuilt, mutation_waited, projection_waited = _run_race(
        migration_database,
        context,
        ready,
        ticket_id,
        version,
        priority,
        finalize_command,
        work_command,
    )
    assert isinstance(result, CtowerProjectReconciliationResult)
    assert mutation_waited
    assert projection_waited
    assert isinstance(changed, WorkReceipt)
    assert rebuilt == _CHECKPOINT_COUNT
    positions = _event_positions(
        migration_database,
        finalize_command,
        work_command,
    )
    assert positions[finalize_command] < positions[work_command]
    assert all(str(work_command) not in fact for fact in result.actual_graph.priority_facts)


def _ready_run(
    database: Database,
    tmp_path: Path,
) -> tuple[spine._RunContext, CtowerProjectImportRun]:
    context = spine._start_run(database, tmp_path)
    importer, plan = spine._bind_reviewed_plan(context, database)
    first = execute_import(
        plan,
        client=spine._MigrationClient(context.migration, importer),
        apply=True,
    )
    assert isinstance(first, ImportPassReceipt)
    refresh_checkpoint_truth(database, now=datetime.now(UTC))
    second = execute_import(
        plan,
        client=spine._MigrationClient(context.migration, importer),
        apply=True,
    )
    assert isinstance(second, ImportPassReceipt)
    ready = context.migration.get_run(context.operator, context.created.run_id)
    assert isinstance(ready, CtowerProjectImportRun)
    return context, ready


def _run_race(
    database: Database,
    context: spine._RunContext,
    ready: CtowerProjectImportRun,
    ticket_id: UUID,
    version: int,
    priority: str,
    finalize_command: UUID,
    work_command: UUID,
) -> tuple[object, object, int, bool, bool]:
    _install_barrier(database)
    barrier = psycopg.connect(database.admin_dsn, autocommit=True)
    barrier.execute("SELECT pg_advisory_lock(%s)", (_BARRIER_KEY,))
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            finalization = executor.submit(
                context.migration.finalize_run,
                context.operator,
                spine._finalize(ready, spine._reconciliation_artifact(context, ready)),
                command_id=finalize_command,
                telemetry=spine._telemetry(context.operator),
            )
            _wait_for_barrier(database)
            mutation = executor.submit(
                _change_priority,
                database,
                context.operator,
                ticket_id,
                version,
                priority,
                work_command,
            )
            projection = executor.submit(
                PostgresProjections(database.projection_dsn).rebuild_project_delivery,
                database.tenant_id,
                now=datetime.now(UTC),
            )
            time.sleep(0.2)
            waited = not mutation.done(), not projection.done()
            barrier.execute("SELECT pg_advisory_unlock(%s)", (_BARRIER_KEY,))
            return (
                finalization.result(timeout=20),
                mutation.result(timeout=20),
                projection.result(timeout=20),
                *waited,
            )
    finally:
        barrier.execute("SELECT pg_advisory_unlock(%s)", (_BARRIER_KEY,))
        barrier.close()
        _remove_barrier(database)


def _bound_ticket(database: Database, run_id: UUID) -> tuple[UUID, int, str]:
    with psycopg.connect(database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT ticket.ticket_id, ticket.version, ticket.priority
            FROM ticket_project_bindings AS binding
            JOIN tickets AS ticket
              ON ticket.tenant_id = binding.tenant_id
             AND ticket.ticket_id = binding.ticket_id
            WHERE binding.run_id = %s
            ORDER BY ticket.ticket_id LIMIT 1
            """,
            (run_id,),
        ).fetchone()
    assert row is not None
    return row[0], int(row[1]), str(row[2])


def _change_priority(
    database: Database,
    actor: Actor,
    ticket_id: UUID,
    version: int,
    priority: str,
    command_id: UUID,
) -> WorkReceipt | RecordProblem:
    work = Work(
        PostgresRecord(database.runtime_dsn),
        writer=PostgresWork(database.runtime_dsn),
    )
    command = ChangePriority(
        client_command_id=command_id,
        ticket_id=ticket_id,
        expected_version=version,
        reason="prove reconciliation target serialization",
        priority="P1" if priority != "P1" else "P2",
    )
    return work.execute(actor, command, telemetry=spine._telemetry(actor))


def _install_barrier(database: Database) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            f"""
            CREATE FUNCTION ctower_test_pause_reconciliation() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_advisory_xact_lock({_BARRIER_KEY});
                RETURN NEW;
            END
            $$;
            CREATE TRIGGER ctower_test_pause_reconciliation
            BEFORE INSERT ON migration_reconciliation_facts
            FOR EACH ROW EXECUTE FUNCTION ctower_test_pause_reconciliation()
            """
        )


def _remove_barrier(database: Database) -> None:
    with psycopg.connect(database.admin_dsn) as connection:
        connection.execute(
            """
            DROP TRIGGER ctower_test_pause_reconciliation
                ON migration_reconciliation_facts;
            DROP FUNCTION ctower_test_pause_reconciliation()
            """
        )


def _wait_for_barrier(database: Database) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with psycopg.connect(database.admin_dsn) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM pg_stat_activity
                WHERE datname = current_database()
                  AND wait_event_type = 'Lock'
                  AND wait_event = 'advisory'
                  AND query LIKE '%INSERT INTO migration_reconciliation_facts%'
                """
            ).fetchone()
        if row is not None:
            return
        time.sleep(0.02)
    raise AssertionError("finalization did not reach the post-capture barrier")


def _event_positions(
    database: Database,
    finalize_command: UUID,
    work_command: UUID,
) -> dict[UUID, int]:
    with psycopg.connect(database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT client_command_id, record_position FROM events
            WHERE client_command_id = ANY(%s)
            """,
            ([finalize_command, work_command],),
        ).fetchall()
    return {row[0]: int(row[1]) for row in rows}
