"""Running-instance proof for one authored Routine occurrence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import ControlWorker, build_worker, load_routine_revisions
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.runtime import Routine, RoutineRevision
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).parents[3]


def test_running_worker_records_one_due_routine_across_duplicate_scan_and_restart(
    tenant: TenantFixture,
) -> None:
    """AC-RWI-01/06: an authored beat reference fires one item through the real worker."""

    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    health = _health_revision()
    runtime.register(tenant.tenant_id, health, first_fire_at=_due_fire(health))
    worker = _worker(tenant, runtime)

    worker.tick()
    first = _work_item_rows(tenant, health)
    worker.tick()
    _worker(tenant, runtime).tick()
    replay = _work_item_rows(tenant, health)

    assert len(first) == 1
    assert replay == first
    assert first[0][1] == health.routine_ref
    assert first[0][2] == "open"
    assert _occurrence_rows(tenant, health) == [(first[0][3], "queued")]
    print(
        f"ROUTINE-E2E revision={health.revision_digest} routine={health.routine_ref} "
        f"work_item={first[0][0]} outcome=queued duplicate_restart_count=1"
    )


def test_ct_i1_006_worker_world_does_not_auto_register_migration_packs(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    worker = _worker(tenant, runtime)

    worker.tick()

    assert _registered_routine_refs(tenant) == []


def _worker(tenant: TenantFixture, runtime: Routine) -> ControlWorker:
    projections = Projections(PostgresProjections(tenant.database.projection_dsn))
    return build_worker(
        runtime,
        projections,
        pack_root=_ROOT / "packs",
        routine_revisions=(),
    )


def _health_revision() -> RoutineRevision:
    return next(
        revision
        for revision in load_routine_revisions(_ROOT / "packs")
        if revision.routine_ref == "ctower.beat.health@1"
    )


def _due_fire(revision: RoutineRevision) -> datetime:
    due = datetime.now(UTC).replace(second=0, microsecond=0)
    while due.minute not in revision.minute_marks:
        due -= timedelta(minutes=1)
    return due


def _work_item_rows(
    tenant: TenantFixture, revision: RoutineRevision
) -> list[tuple[object, object, object, object]]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT work_item_id::text, routine_ref, status, scheduled_for
            FROM inbox_work_items
            WHERE tenant_id = %s AND revision_digest = %s
            ORDER BY scheduled_for
            """,
            (tenant.tenant_id, _digest(revision)),
        ).fetchall()
    return [tuple(row) for row in rows]


def _occurrence_rows(
    tenant: TenantFixture, revision: RoutineRevision
) -> list[tuple[object, object]]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT scheduled_for, outcome FROM routine_occurrences
            WHERE tenant_id = %s AND revision_digest = %s
            ORDER BY scheduled_for
            """,
            (tenant.tenant_id, _digest(revision)),
        ).fetchall()
    return [tuple(row) for row in rows]


def _digest(revision: RoutineRevision) -> bytes:
    return bytes.fromhex(revision.revision_digest.removeprefix("sha256:"))


def _registered_routine_refs(tenant: TenantFixture) -> list[str]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT revision.routine_ref
            FROM routine_triggers AS trigger
            JOIN routine_revisions AS revision
              ON revision.revision_digest = trigger.revision_digest
            WHERE trigger.tenant_id = %s
            ORDER BY revision.routine_ref
            """,
            (tenant.tenant_id,),
        ).fetchall()
    return [str(row[0]) for row in rows]
