"""AC-RWI-05: the append-only alarm episode over real PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from support.routine_items import (
    close_window,
    expire_window,
    past_minute_mark,
    read_alarm_rows,
    revision,
    single_mark_revision,
)
from support.tenant_fixture import TenantFixture, provision_seat

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.runtime import Routine
from ctower_kernel.runtime.items import (
    CompleteRoutineWorkItemCommand,
    RoutineAlarmEpisode,
    RoutineWorkItem,
    RoutineWorkItemReceipt,
)
from ctower_kernel.runtime.postgres import PostgresRuntime

__all__: tuple[str, ...] = ()


def test_ac_rwi_05_expired_window_raises_one_ordinary_alarm_under_replay_and_restart(
    tenant: TenantFixture,
) -> None:
    """Sequential, replay, and restart attempts on one stable key add one ordinary fact."""

    runtime, item = _fired_item(tenant)
    ended = expire_window(tenant, item.work_item_id)
    assert ended > item.scheduled_for

    first = runtime.scan(tenant.tenant_id)
    assert [alarm.kind.value for alarm in first.work_item_alarms] == ["missed_window"]
    alarm = first.work_item_alarms[0]
    assert alarm.work_item_id == item.work_item_id
    assert alarm.escalation_seat == "ctower-commander"
    assert alarm.revision_digest == item.revision_digest
    assert alarm.unresolved_reason is None

    assert runtime.scan(tenant.tenant_id).work_item_alarms == ()
    restarted = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    assert restarted.scan(tenant.tenant_id).work_item_alarms == ()

    episode = _only_episode(restarted, tenant)
    assert episode.state.value == "confirmed-unconsumed"
    assert episode.ordinary_alarms == 1
    assert read_alarm_rows(tenant) == [("missed_window", None)]


def test_ac_rwi_05_two_concurrent_boundary_attempts_add_one_ordinary_fact(
    tenant: TenantFixture,
) -> None:
    """At least two concurrent attempts per stable key still record exactly one alarm."""

    runtime, item = _fired_item(tenant)
    expire_window(tenant, item.work_item_id)
    stores = [PostgresRuntime(tenant.database.runtime_dsn) for _ in range(2)]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(store.scan, tenant.tenant_id) for store in stores]
        scans = [future.result() for future in futures]

    raised = [alarm for scan in scans for alarm in scan.work_item_alarms]
    assert [alarm.kind.value for alarm in raised] == ["missed_window"]
    assert _only_episode(runtime, tenant).ordinary_alarms == 1


def test_ac_rwi_05_receipt_before_and_on_the_boundary_never_alarms(
    tenant: TenantFixture,
) -> None:
    """A window closed by a receipt opens no episode, at or before its boundary."""

    runtime, item = _fired_item(tenant)
    receipt = _complete(runtime, tenant, item, "artifact:before-boundary")

    assert runtime.scan(tenant.tenant_id).work_item_alarms == ()
    close_window(tenant, item.work_item_id, receipt.delivered_at)
    assert runtime.scan(tenant.tenant_id).work_item_alarms == ()

    assert runtime.alarm_episodes(tenant.tenant_id) == ()
    assert read_alarm_rows(tenant) == []


def test_ac_rwi_05_receipt_after_the_boundary_leaves_one_ordinary_alarm(
    tenant: TenantFixture,
) -> None:
    """A late receipt closes the item without erasing or duplicating the ordinary alarm."""

    runtime, item = _fired_item(tenant)
    expire_window(tenant, item.work_item_id)
    assert [alarm.kind.value for alarm in runtime.scan(tenant.tenant_id).work_item_alarms] == [
        "missed_window"
    ]

    receipt = _complete(runtime, tenant, item, "artifact:after-boundary")

    assert receipt.work_item_id == item.work_item_id
    assert runtime.scan(tenant.tenant_id).work_item_alarms == ()
    episode = _only_episode(runtime, tenant)
    assert episode.state.value == "confirmed-unconsumed"
    assert episode.ordinary_alarms == 1
    assert read_alarm_rows(tenant) == [("missed_window", None)]


def test_ac_rwi_05_degraded_read_resolves_to_confirmed_unconsumed(
    tenant: TenantFixture,
) -> None:
    """A partial read opens the episode; the later authoritative read resolves it."""

    runtime, item = _fired_item(tenant)
    evidence = _blank_gate_evidence(tenant, item.work_item_id)
    degraded = runtime.scan(tenant.tenant_id)

    assert [alarm.kind.value for alarm in degraded.work_item_alarms] == ["degraded_read"]
    assert _only_episode(runtime, tenant).state.value == "degraded"
    assert _only_episode(runtime, tenant).ordinary_alarms == 0

    _restore_gate_evidence(tenant, item.work_item_id, evidence)
    expire_window(tenant, item.work_item_id)
    resolved = runtime.scan(tenant.tenant_id)

    assert [alarm.kind.value for alarm in resolved.work_item_alarms] == ["missed_window"]
    episode = _only_episode(runtime, tenant)
    assert episode.state.value == "confirmed-unconsumed"
    assert episode.ordinary_alarms == 1
    assert read_alarm_rows(tenant) == [("degraded_read", None), ("missed_window", None)]


def test_ac_rwi_05_degraded_read_resolves_to_recovered_receipted(
    tenant: TenantFixture,
) -> None:
    """A receipt accepted after a partial read resolves the episode with no ordinary alarm."""

    runtime, item = _fired_item(tenant)
    _blank_gate_evidence(tenant, item.work_item_id)
    assert [alarm.kind.value for alarm in runtime.scan(tenant.tenant_id).work_item_alarms] == [
        "degraded_read"
    ]

    _complete(runtime, tenant, item, "artifact:recovered")
    recovered = runtime.scan(tenant.tenant_id)

    assert [alarm.kind.value for alarm in recovered.work_item_alarms] == ["recovered_receipted"]
    episode = _only_episode(runtime, tenant)
    assert episode.state.value == "recovered-receipted"
    assert episode.ordinary_alarms == 0
    assert runtime.scan(tenant.tenant_id).work_item_alarms == ()
    assert read_alarm_rows(tenant) == [("degraded_read", None), ("recovered_receipted", None)]


def test_ac_rwi_05_binding_supersession_alarms_to_the_active_revision_seat(
    tenant: TenantFixture,
) -> None:
    """The binding is published by the Routine revision and is never caller-selected."""

    runtime, item = _fired_item(tenant)
    assert item.escalation_seat == "ctower-commander"
    provision_seat(tenant, "watch-commander")
    superseded = revision(escalation_seat="watch-commander", digest_seed="c")
    runtime.register(
        tenant.tenant_id, superseded, first_fire_at=datetime.now(UTC) + timedelta(hours=2)
    )
    expire_window(tenant, item.work_item_id)

    scan = runtime.scan(tenant.tenant_id)

    assert [alarm.escalation_seat for alarm in scan.work_item_alarms] == ["watch-commander"]
    assert read_alarm_rows(tenant) == [("missed_window", None)]
    assert _stored_escalation_seats(tenant) == {"ctower-commander", "watch-commander"}


def test_ac_rwi_05_missing_binding_refuses_to_claim_delivery(tenant: TenantFixture) -> None:
    _assert_unresolved(tenant, "never-registered-seat", "missing", project=None)


def test_ac_rwi_05_foreign_scope_binding_refuses_to_claim_delivery(
    tenant: TenantFixture,
) -> None:
    _assert_unresolved(tenant, "foreign-commander", "foreign_scope", project="other-project")


def test_ac_rwi_05_revoked_binding_refuses_to_claim_delivery(tenant: TenantFixture) -> None:
    _assert_unresolved(tenant, "revoked-commander", "revoked", project="ctower")


def test_ac_rwi_05_stale_binding_refuses_then_resolves_when_republished(
    tenant: TenantFixture,
) -> None:
    """A window whose Routine has no active revision cannot claim any delivery."""

    runtime, item = _fired_item(tenant)
    expire_window(tenant, item.work_item_id)
    _drop_active_registration(tenant)

    stale = runtime.scan(tenant.tenant_id)

    assert [alarm.kind.value for alarm in stale.work_item_alarms] == ["escalation_unresolved"]
    reason = stale.work_item_alarms[0].unresolved_reason
    assert reason is not None and reason.value == "stale"
    assert _only_episode(runtime, tenant).state.value == "escalation-unresolved"
    assert _only_episode(runtime, tenant).ordinary_alarms == 0

    runtime.register(
        tenant.tenant_id,
        single_mark_revision(item.scheduled_for),
        first_fire_at=datetime.now(UTC) + timedelta(hours=2),
    )
    republished = runtime.scan(tenant.tenant_id)

    assert [alarm.kind.value for alarm in republished.work_item_alarms] == ["missed_window"]
    episode = _only_episode(runtime, tenant)
    assert episode.state.value == "confirmed-unconsumed"
    assert episode.ordinary_alarms == 1


def _assert_unresolved(
    tenant: TenantFixture, seat: str, reason: str, *, project: str | None
) -> None:
    if project is not None:
        principal_id, _ = provision_seat(tenant, seat, project_key=project)
        if reason == "revoked":
            _revoke_credentials(tenant, principal_id)
    runtime, item = _fired_item(tenant, escalation_seat=seat)
    expire_window(tenant, item.work_item_id)

    scan = runtime.scan(tenant.tenant_id)

    assert [alarm.kind.value for alarm in scan.work_item_alarms] == ["escalation_unresolved"]
    alarm = scan.work_item_alarms[0]
    assert alarm.unresolved_reason is not None and alarm.unresolved_reason.value == reason
    assert alarm.escalation_seat == seat
    episode = _only_episode(runtime, tenant)
    assert episode.state.value == "escalation-unresolved"
    assert episode.ordinary_alarms == 0
    assert read_alarm_rows(tenant) == [("escalation_unresolved", reason)]
    assert runtime.scan(tenant.tenant_id).work_item_alarms == ()


def _fired_item(
    tenant: TenantFixture, *, escalation_seat: str = "ctower-commander"
) -> tuple[Routine, RoutineWorkItem]:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    due = past_minute_mark()
    runtime.register(
        tenant.tenant_id,
        single_mark_revision(due, escalation_seat=escalation_seat),
        first_fire_at=due,
    )
    item = runtime.scan(tenant.tenant_id).work_items[0]
    assert item.scheduled_for == due
    return runtime, item


def _complete(
    runtime: Routine, tenant: TenantFixture, item: RoutineWorkItem, artifact: str
) -> RoutineWorkItemReceipt:
    owner = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    receipt = runtime.complete_routine_work_item(
        owner, CompleteRoutineWorkItemCommand(uuid4(), item.work_item_id, artifact)
    )
    assert not isinstance(receipt, RecordProblem)
    return receipt


def _only_episode(runtime: Routine, tenant: TenantFixture) -> RoutineAlarmEpisode:
    episodes = runtime.alarm_episodes(tenant.tenant_id)
    assert len(episodes) == 1
    return episodes[0]


def _blank_gate_evidence(tenant: TenantFixture, work_item_id: UUID) -> object:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT gate_evidence FROM inbox_work_items WHERE work_item_id = %s",
            (work_item_id,),
        ).fetchone()
        connection.execute(
            "UPDATE inbox_work_items SET gate_evidence = '{}'::jsonb WHERE work_item_id = %s",
            (work_item_id,),
        )
        connection.commit()
    assert row is not None
    return row[0]


def _restore_gate_evidence(tenant: TenantFixture, work_item_id: UUID, evidence: object) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE inbox_work_items SET gate_evidence = %s WHERE work_item_id = %s",
            (Jsonb(evidence), work_item_id),
        )
        connection.commit()


def _stored_escalation_seats(tenant: TenantFixture) -> set[str]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute("SELECT escalation_seat FROM routine_item_specs").fetchall()
    return {str(row[0]) for row in rows}


def _drop_active_registration(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute("DELETE FROM routine_triggers WHERE tenant_id = %s", (tenant.tenant_id,))
        connection.commit()


def _revoke_credentials(tenant: TenantFixture, principal_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE principal_credentials SET revoked_at = now() WHERE principal_id = %s",
            (principal_id,),
        )
        connection.commit()
