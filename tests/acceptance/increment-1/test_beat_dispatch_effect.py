"""Stage-walked fleet-beat registration, emission, and operator read proof."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import cast
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from support.beat_retirement import (
    RetirementReceipt,
    api_cli_retirement,
    beat_revisions,
    due_mark,
    non_operator_principals,
    retire,
    retirement_is_immutable,
    retirement_lineage_counts,
    retirement_protected_counts,
    routine_snapshot,
    set_principal_disabled,
)
from support.tenant_fixture import TenantFixture

from ctower_api.control_worker import load_routine_revisions
from ctower_api.interface import create_app
from ctower_client import CtowerClient
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
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


def test_operator_retires_active_beat_append_only_and_future_ticks_do_not_reactivate(
    tenant: TenantFixture,
) -> None:
    beats = beat_revisions()
    target = beats["health"]
    unrelated = beats["director-drive"]
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    due = due_mark(target)
    future = datetime.now(UTC) + timedelta(days=1)
    runtime.register(tenant.tenant_id, target, first_fire_at=due)
    runtime.register(tenant.tenant_id, unrelated, first_fire_at=future)
    emitted = runtime.scan(tenant.tenant_id)
    assert [effect.routine_ref for effect in emitted.beat_dispatches] == [target.routine_ref]
    before = routine_snapshot(tenant, target.routine_ref, unrelated.routine_ref)

    receipt, cli_status = api_cli_retirement(tenant, store, target)
    assert receipt.routine_ref == target.routine_ref
    assert receipt.revision_digest == target.revision_digest

    # This is the exact worker-tick shape that used to resurrect a deleted trigger.
    runtime.register(tenant.tenant_id, target, first_fire_at=due)
    after_tick = runtime.scan(tenant.tenant_id)
    assert all(item.routine_ref != target.routine_ref for item in after_tick.occurrences)
    assert all(item.routine_ref != target.routine_ref for item in after_tick.beat_dispatches)
    after = routine_snapshot(tenant, target.routine_ref, unrelated.routine_ref)

    assert after.revisions == before.revisions
    assert after.occurrences == before.occurrences
    assert after.effects == before.effects
    assert before.target_triggers == (target.revision_digest,)
    assert after.target_triggers == ()
    assert after.unrelated_trigger_count == before.unrelated_trigger_count == 1
    assert retirement_lineage_counts(tenant, receipt.command_id, receipt.retirement_id) == (
        1,
        1,
        1,
        1,
    )
    print(
        "TEST-POSTGRES beat_retire revisions="
        f"{len(after.revisions)} occurrences={len(after.occurrences)} "
        f"effects={len(after.effects)} target_triggers=0 unrelated_triggers=1 "
        f"retirement_id={receipt.retirement_id} api_cli=identical cli_exit={cli_status}"
    )


def test_beat_retirement_replay_and_refusal_matrix(
    tenant: TenantFixture,
    second_tenant: TenantFixture,
) -> None:
    beats = beat_revisions()
    target = beats["health"]
    foreign = beats["director-drive"]
    store = PostgresRuntime(tenant.database.runtime_dsn)
    future = datetime.now(UTC) + timedelta(days=1)
    Routine(store).register(tenant.tenant_id, target, first_fire_at=future)
    Routine(store).register(second_tenant.tenant_id, foreign, first_fire_at=future)
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    command_id = uuid4()

    first = retire(store, operator, command_id, target.routine_ref)
    assert not isinstance(first, RecordProblem)
    replay = retire(store, operator, command_id, target.routine_ref)
    assert replay == first
    set_principal_disabled(tenant, disabled=True)
    disabled_replay = retire(store, operator, command_id, target.routine_ref)
    set_principal_disabled(tenant, disabled=False)
    assert isinstance(disabled_replay, RecordProblem)
    assert (disabled_replay.status, disabled_replay.code) == (403, "beat-routine-retire-forbidden")
    protected_after_retirement = retirement_protected_counts(tenant)
    changed = retire(store, operator, command_id, foreign.routine_ref)
    assert isinstance(changed, RecordProblem)
    assert (changed.status, changed.code) == (409, "idempotency-conflict")

    already = retire(store, operator, uuid4(), target.routine_ref)
    assert isinstance(already, RecordProblem)
    assert (already.status, already.code) == (409, "beat-routine-already-retired")
    foreign_only = retire(store, operator, uuid4(), foreign.routine_ref)
    assert isinstance(foreign_only, RecordProblem)
    assert (foreign_only.status, foreign_only.code) == (404, "beat-routine-not-found")
    unknown_ref = "ctower.beat.unknown@1"
    unknown = retire(store, operator, uuid4(), unknown_ref)
    assert isinstance(unknown, RecordProblem)
    assert (unknown.status, unknown.code) == (404, "beat-routine-not-found")
    assert retirement_protected_counts(tenant) == protected_after_retirement

    principals = non_operator_principals(tenant)
    authority_cases = [
        (tenant.commander_id, cast(PrincipalKind, "commander")),
        *[(principal_id, cast(PrincipalKind, kind)) for kind, principal_id in principals.items()],
        # Actor.kind is a request value too: persisted Commander authority still wins.
        (tenant.commander_id, PrincipalKind.OPERATOR),
    ]
    for principal_id, claimed_kind in authority_cases:
        refused = retire(
            store,
            Actor(principal_id, tenant.tenant_id, claimed_kind),
            uuid4(),
            unknown_ref,
        )
        assert isinstance(refused, RecordProblem)
        assert (refused.status, refused.code) == (403, "beat-routine-retire-forbidden")
    assert retirement_protected_counts(tenant) == protected_after_retirement
    print(
        "TEST-POSTGRES beat_retire replay=identical changed_body=idempotency-conflict "
        "already=409 unknown=404 foreign_only=404 authority_refusals="
        f"{len(authority_cases)} disclosure=forbidden-first"
    )


def test_retirement_linearizes_against_register_scan_and_rollback_insert(
    tenant: TenantFixture,
) -> None:
    target = beat_revisions()["sprint"]
    store = PostgresRuntime(tenant.database.runtime_dsn)
    runtime = Routine(store)
    due = due_mark(target)
    runtime.register(tenant.tenant_id, target, first_fire_at=due)
    barrier = Barrier(3)
    command_id = uuid4()
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)

    def register_many() -> None:
        barrier.wait()
        for _ in range(24):
            runtime.register(tenant.tenant_id, target, first_fire_at=due)

    def scan_many() -> None:
        barrier.wait()
        for _ in range(24):
            runtime.scan(tenant.tenant_id)

    def retire_once() -> object:
        barrier.wait()
        return retire(store, operator, command_id, target.routine_ref)

    with ThreadPoolExecutor(max_workers=3) as executor:
        registration = executor.submit(register_many)
        scanning = executor.submit(scan_many)
        retirement = executor.submit(retire_once)
        outcome = retirement.result(timeout=30)
        registration.result(timeout=30)
        scanning.result(timeout=30)
    assert not isinstance(outcome, RecordProblem)
    receipt = cast(RetirementReceipt, outcome)

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rollback_insert = connection.execute(
            """
            INSERT INTO routine_triggers (
                tenant_id, revision_digest, next_fire_at, updated_at
            ) VALUES (%s, %s, %s, transaction_timestamp())
            """,
            (
                tenant.tenant_id,
                bytes.fromhex(target.revision_digest.removeprefix("sha256:")),
                due,
            ),
        )
        assert rollback_insert.rowcount == 0

    runtime.register(tenant.tenant_id, target, first_fire_at=due)
    assert runtime.scan(tenant.tenant_id).beat_dispatches == ()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        state = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM routine_retirements
                WHERE tenant_id = %s AND routine_ref = %s),
              (SELECT count(*) FROM routine_triggers AS trigger
                 JOIN routine_revisions AS revision USING (revision_digest)
                WHERE trigger.tenant_id = %s AND revision.routine_ref = %s),
              (SELECT count(*) FROM routine_occurrences AS occurrence
                 JOIN routine_revisions AS revision USING (revision_digest)
                WHERE occurrence.tenant_id = %s AND revision.routine_ref = %s
                  AND occurrence.recorded_at > %s),
              (SELECT count(*) FROM runtime_beat_dispatch_effects
                WHERE tenant_id = %s AND routine_ref = %s AND emitted_at > %s)
            """,
            (
                tenant.tenant_id,
                target.routine_ref,
                tenant.tenant_id,
                target.routine_ref,
                tenant.tenant_id,
                target.routine_ref,
                receipt.retired_at,
                tenant.tenant_id,
                target.routine_ref,
                receipt.retired_at,
            ),
        ).fetchone()
    assert state == (1, 0, 0, 0)
    retirement_is_immutable(tenant, receipt.retirement_id)
    print(
        "TEST-POSTGRES beat_retire concurrent_registers=24 concurrent_scans=24 "
        "retirements=1 active_triggers=0 post_cutover_occurrences=0 "
        "post_cutover_effects=0 rollback_insert_rows=0 retirement_update_delete=refused"
    )
