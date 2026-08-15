"""Running-instance proof for one authored Routine occurrence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import psycopg
from fastapi.testclient import TestClient
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import ControlWorker, build_worker, load_routine_revisions
from ctower_api.interface import create_app
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.runtime import Routine, RoutineRevision
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()

_ROOT = Path(__file__).parents[3]
_HTTP_OK = 200


def test_running_worker_records_one_due_routine_across_duplicate_scan_and_restart(
    tenant: TenantFixture,
) -> None:
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    health = _health_revision()
    runtime.register(tenant.tenant_id, health, first_fire_at=_due_fire(health))
    worker = _worker(tenant, runtime)
    app = create_app(
        PostgresRecord(tenant.database.runtime_dsn),
        beat_dispatch_runtime=store,
    )

    with TestClient(app) as client:
        assert _effects(client, tenant.operator_credential) == []
        worker.tick()
        first_read = _effects(client, tenant.operator_credential)
        assert len(first_read) == 1
        first = first_read[0]
        routines = _routines(client, tenant.operator_credential)
        worker.tick()
        restarted = _worker(tenant, runtime)
        restarted.tick()
        replay = _effects(client, tenant.operator_credential)

    assert replay == [first]
    health_routines = [
        routine for routine in routines if routine["routine_ref"] == health.routine_ref
    ]
    assert len(health_routines) == 1
    assert health_routines[0]["revision_digest"] == health.revision_digest
    assert first["routine_ref"] == health.routine_ref
    assert first["revision_digest"] == health.revision_digest
    assert _durable_rows(tenant, health) == [(first["occurrence_id"], "queued", "beat_dispatch")]
    print(
        f"ROUTINE-E2E revision={health.revision_digest} occurrence_id=<occurrence-id> "
        "outcome=queued effect=beat_dispatch duplicate_restart_count=1"
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


def _effects(client: TestClient, credential: str) -> list[dict[str, object]]:
    payload = _get(client, "/v1/runtime/beat-dispatches", credential)
    return cast(list[dict[str, object]], payload["effects"])


def _routines(client: TestClient, credential: str) -> list[dict[str, object]]:
    payload = _get(client, "/v1/runtime/beat-routines", credential)
    return cast(list[dict[str, object]], payload["routines"])


def _get(client: TestClient, path: str, credential: str) -> dict[str, object]:
    response = client.get(path, headers={"Authorization": f"Bearer {credential}"})
    assert response.status_code == _HTTP_OK, (
        f"running ctower returned {response.status_code}, including disabled/503"
    )
    return cast(dict[str, object], response.json())


def _durable_rows(
    tenant: TenantFixture,
    revision: RoutineRevision,
) -> list[tuple[object, object, object]]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT occurrence.occurrence_id::text, occurrence.outcome, job.operation
            FROM routine_occurrences AS occurrence
            JOIN operation_jobs AS job USING (tenant_id, occurrence_id)
            WHERE occurrence.tenant_id = %s AND occurrence.revision_digest = %s
            ORDER BY occurrence.scheduled_for
            """,
            (tenant.tenant_id, bytes.fromhex(revision.revision_digest.removeprefix("sha256:"))),
        ).fetchall()
    return [tuple(row) for row in rows]


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
