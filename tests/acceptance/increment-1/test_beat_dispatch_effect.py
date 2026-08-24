"""Stage-walked fleet-beat registration, emission, and operator read proof."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import build_worker, load_routine_revisions
from ctower_api.interface import create_app
from ctower_client import CtowerClient
from ctower_kernel.projections import Projections
from ctower_kernel.projections.postgres import PostgresProjections
from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.runtime import Routine
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()
_BEAT_COUNT = 5
_HTTP_NOT_FOUND = 404
_HTTP_PENDING = 202


def _assert_retired_pack_reboot(
    root: Path,
    tmp_path: Path,
    tenant: TenantFixture,
    runtime: Routine,
    store: PostgresRuntime,
    routine_ref: str,
) -> None:
    assert store.fully_retired_routine_refs() == (routine_ref,)
    shadow_packs = tmp_path / "packs"
    shutil.copytree(root / "packs", shadow_packs)
    (shadow_packs / "routines/ctower.beat.health/v1.yaml").unlink()
    worker = build_worker(
        runtime,
        Projections(PostgresProjections(tenant.database.projection_dsn)),
        pack_root=shadow_packs,
    )
    assert routine_ref not in {revision.routine_ref for revision in worker.routine_loop.revisions}


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


def test_corrected_beat_revision_replaces_only_the_active_trigger(
    tenant: TenantFixture,
) -> None:
    root = Path(__file__).parents[3]
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    corrected = next(
        revision
        for revision in load_routine_revisions(root / "packs")
        if revision.routine_ref == "ctower.beat.digest@1"
    )
    stale = replace(
        corrected,
        revision_digest="sha256:861bb079c7223bcc43e2c2d8ae883f6d41bf30a0e3077a6fb87e9b4500b7c6b9",
        timezone="UTC",
    )
    due = datetime.now(UTC).replace(second=0, microsecond=0)

    runtime.register(tenant.tenant_id, stale, first_fire_at=due)
    emitted = runtime.scan(tenant.tenant_id).beat_dispatches
    runtime.register(tenant.tenant_id, corrected)

    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    listed = store.list_beat_routines(operator)
    assert [(item.routine_ref, item.revision_digest, item.timezone) for item in listed] == [
        (corrected.routine_ref, corrected.revision_digest, "Europe/Vilnius")
    ]
    assert len(emitted) == 1
    assert [item.effect_id for item in store.list_beat_dispatches(operator)] == [
        emitted[0].effect_id
    ]

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM routine_revisions WHERE routine_ref = %s),
              (SELECT count(*) FROM routine_beat_dispatch_specs WHERE beat_key = 'digest'),
              (SELECT count(*)
                 FROM routine_triggers AS trigger
                 JOIN routine_revisions AS revision USING (revision_digest)
                WHERE trigger.tenant_id = %s AND revision.routine_ref = %s)
            """,
            (corrected.routine_ref, tenant.tenant_id, corrected.routine_ref),
        ).fetchone()
    assert counts == (2, 2, 1)


def test_retiring_live_beat_is_append_only_and_prevents_later_occurrences(
    tenant: TenantFixture,
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[3]
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    health = next(
        revision
        for revision in load_routine_revisions(root / "packs")
        if revision.routine_ref == "ctower.beat.health@1"
    )
    due = datetime.now(UTC).replace(second=0, microsecond=0)
    runtime.register(tenant.tenant_id, health, first_fire_at=due)
    command_id = uuid4()
    record = PostgresRecord(tenant.database.runtime_dsn)

    with TestClient(create_app(record, beat_dispatch_runtime=store)) as client:
        response = client.post(
            f"/v1/runtime/beat-routines/{health.routine_ref}/retire",
            json={},
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        )
        replay = client.post(
            f"/v1/runtime/beat-routines/{health.routine_ref}/retire",
            json={},
            headers={
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
                **telemetry_headers(command_id),
            },
        )

    assert response.status_code == replay.status_code == _HTTP_PENDING
    assert response.json() == replay.json()
    assert response.json()["routine_ref"] == health.routine_ref
    assert response.json()["revision_digest"] == health.revision_digest

    runtime.register(tenant.tenant_id, health, first_fire_at=due)
    scan = runtime.scan(tenant.tenant_id)
    assert scan.occurrences == ()
    assert scan.beat_dispatches == ()
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    assert store.list_beat_routines(operator) == ()
    _assert_retired_pack_reboot(root, tmp_path, tenant, runtime, store, health.routine_ref)

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM routine_retirements WHERE tenant_id = %s),
              (SELECT count(*) FROM routine_triggers WHERE tenant_id = %s),
              (SELECT count(*) FROM routine_revisions WHERE revision_digest = %s),
              (SELECT count(*) FROM routine_occurrences WHERE tenant_id = %s)
            """,
            (
                tenant.tenant_id,
                tenant.tenant_id,
                bytes.fromhex(health.revision_digest.removeprefix("sha256:")),
                tenant.tenant_id,
            ),
        ).fetchone()
        assert counts == (1, 0, 1, 0)
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState, match="immutable"):
            connection.execute(
                "UPDATE routine_retirements SET retired_at = transaction_timestamp() "
                "WHERE tenant_id = %s",
                (tenant.tenant_id,),
            )
    print(
        "TEST-POSTGRES beat_retirement=1 active_triggers=0 later_occurrences=0 "
        "immutable_revision=preserved retired_pack=absent reboot=ok"
    )


def test_retiring_unknown_or_foreign_beat_returns_the_same_typed_refusal(
    tenant: TenantFixture,
    second_tenant: TenantFixture,
) -> None:
    root = Path(__file__).parents[3]
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    health = next(
        revision
        for revision in load_routine_revisions(root / "packs")
        if revision.routine_ref == "ctower.beat.health@1"
    )
    runtime.register(second_tenant.tenant_id, health)
    record = PostgresRecord(tenant.database.runtime_dsn)

    with TestClient(create_app(record, beat_dispatch_runtime=store)) as client:
        problems = []
        for routine_ref in (health.routine_ref, "ctower.beat.unknown@1"):
            command_id = uuid4()
            response = client.post(
                f"/v1/runtime/beat-routines/{routine_ref}/retire",
                json={},
                headers={
                    "Authorization": f"Bearer {tenant.operator_credential}",
                    "Idempotency-Key": str(command_id),
                    **telemetry_headers(command_id),
                },
            )
            assert response.status_code == _HTTP_NOT_FOUND
            problems.append(response.json())

    assert [problem["code"] for problem in problems] == [
        "beat-routine-not-found",
        "beat-routine-not-found",
    ]
    assert [problem["title"] for problem in problems] == [
        "Beat routine unavailable",
        "Beat routine unavailable",
    ]
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute(
            "SELECT count(*) FROM routine_retirements WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
    assert count == (0,)
