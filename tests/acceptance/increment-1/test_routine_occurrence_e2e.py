"""Running-instance proof for one authored Routine occurrence."""

from __future__ import annotations

from pathlib import Path

import psycopg
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import ControlWorker, build_worker
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.runtime import Routine
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).parents[3]


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
