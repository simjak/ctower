"""Stage-walked fleet-beat registration, emission, and operator read proof."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import load_routine_revisions
from ctower_api.interface import create_app
from ctower_client import CtowerClient
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.runtime import Routine
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()
_BEAT_COUNT = 5


def test_fleet_beat_occurrence_emits_full_prompt_and_operator_lists_registered_routines(
    tenant: TenantFixture,
) -> None:
    root = Path(__file__).parents[3]
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    beats = tuple(
        revision
        for revision in load_routine_revisions(root / "packs")
        if revision.handler_kind == "beat_dispatch"
    )
    health = next(
        revision
        for revision in beats
        if revision.beat_dispatch is not None and revision.beat_dispatch.beat_key == "health"
    )
    assert health.beat_dispatch is not None
    now = datetime.now(UTC)
    due = now.replace(second=0, microsecond=0)
    while due.minute not in health.minute_marks:
        due -= timedelta(minutes=1)

    for revision in beats:
        first_fire = due if revision is health else revision.next_fire_after(now)
        runtime.register(tenant.tenant_id, revision, first_fire_at=first_fire)

    scan = runtime.scan(tenant.tenant_id)
    assert len(scan.beat_dispatches) == 1
    effect = scan.beat_dispatches[0]
    canonical = health.beat_dispatch.prompt
    assert effect.spec.prompt == canonical
    assert effect.spec.prompt_sha256 == "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    assert effect.spec.target_session == "commander"
    assert effect.scheduled_for == due
    assert effect.occurrence_id == scan.occurrences[0].occurrence_id
    assert len(scan.jobs) == 1 and scan.jobs[0].operation == "beat_dispatch"

    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    assert {routine.routine_ref for routine in store.list_beat_routines(operator)} == {
        revision.routine_ref for revision in beats
    }
    assert [listed.effect_id for listed in store.list_beat_dispatches(operator)] == [
        effect.effect_id
    ]

    record = PostgresRecord(tenant.database.runtime_dsn)
    with TestClient(create_app(record, beat_dispatch_runtime=store)) as transport:
        client = CtowerClient(str(transport.base_url), credential=tenant.operator_credential)
        client._http.close()
        client._http = transport
        listed_routines = client.list_beat_routines()
        listed_effects = client.list_beat_dispatch_effects()
    assert len(listed_routines.routines) == _BEAT_COUNT
    assert [listed.effect_id for listed in listed_effects.effects] == [effect.effect_id]

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        job_count = connection.execute(
            """
            SELECT count(*) FROM operation_jobs AS job
            JOIN routine_occurrences AS occurrence USING (occurrence_id, tenant_id)
            WHERE occurrence.revision_digest = %s
            """,
            (bytes.fromhex(health.revision_digest.removeprefix("sha256:")),),
        ).fetchone()
    assert job_count is not None and job_count[0] == 1
    print(
        "TEST-POSTGRES beat_routines=5 health_effects=1 full_prompt=exact "
        "target=commander operation_jobs=1"
    )
