"""AC-RWI-01..05: Routine work items over real PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from support.tenant_fixture import TenantFixture, provision_seat

from ctower_api.control_worker import load_routine_revisions
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    Routine,
    RoutineRevision,
    ScheduleKind,
)
from ctower_kernel.runtime.items import CompleteRoutineWorkItemCommand, RoutineItemSpec
from ctower_kernel.runtime.postgres import PostgresRuntime

ROOT = Path(__file__).parents[3]
__all__: tuple[str, ...] = ()


def test_ac_rwi_01_fire_appends_one_pointer_only_inbox_item_and_replays_zero(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    revision = _revision()
    due = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
    runtime.register(tenant.tenant_id, revision, first_fire_at=due)

    first = runtime.scan(tenant.tenant_id)
    assert [item.routine_ref for item in first.work_items] == [revision.routine_ref]
    item = first.work_items[0]
    assert item.owner_seat == "ctower-commander"
    assert item.knowledge_ref == "routine-test-report"
    assert item.document_id == UUID("00000000-0000-4000-8000-000000000001")
    assert item.gate_evidence.result == "fired"
    assert first.session_writes == ()

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute(
            "SELECT count(*) FROM inbox_work_items WHERE tenant_id = %s", (tenant.tenant_id,)
        ).fetchone()
        assert count is not None and count[0] == 1
        columns = connection.execute(
            """
            SELECT routine_ref, owner_seat, knowledge_ref, document_id, gate_evidence,
                   to_jsonb(inbox_work_items)
            FROM inbox_work_items WHERE tenant_id = %s
            """,
            (tenant.tenant_id,),
        ).fetchone()
        assert columns is not None
        assert columns[0] == revision.routine_ref
        assert columns[1] == "ctower-commander"
        assert columns[2] == "routine-test-report"
        assert columns[3] == UUID("00000000-0000-4000-8000-000000000001")
        assert columns[4]["result"] == "fired"
        assert "prompt" not in columns[5] and "instructions" not in columns[5]

    _reset_trigger(tenant, revision, due)
    replay = runtime.scan(tenant.tenant_id)
    assert replay.work_items == ()
    assert replay.session_writes == ()


def test_ac_rwi_04_completion_requires_owner_receipt_and_is_idempotent(
    tenant: TenantFixture,
) -> None:
    runtime = PostgresRuntime(tenant.database.runtime_dsn)
    revision = _revision()
    due = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
    runtime.register(tenant.tenant_id, revision, first_fire_at=due)
    item = runtime.scan(tenant.tenant_id).work_items[0]

    owner = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    missing = runtime.complete_routine_work_item(
        owner,
        CompleteRoutineWorkItemCommand(UUID(int=1), item.work_item_id, ""),
    )
    assert isinstance(missing, RecordProblem)

    receipt = runtime.complete_routine_work_item(
        owner,
        CompleteRoutineWorkItemCommand(UUID(int=2), item.work_item_id, "artifact:test-report"),
    )
    assert not isinstance(receipt, RecordProblem)
    assert receipt.artifact_ref == "artifact:test-report"

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        before = connection.execute(
            "SELECT status, receipt_artifact_ref FROM inbox_work_items WHERE work_item_id = %s",
            (item.work_item_id,),
        ).fetchone()
    double = runtime.complete_routine_work_item(
        owner,
        CompleteRoutineWorkItemCommand(UUID(int=3), item.work_item_id, "artifact:other"),
    )
    assert isinstance(double, RecordProblem)
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        after = connection.execute(
            "SELECT status, receipt_artifact_ref FROM inbox_work_items WHERE work_item_id = %s",
            (item.work_item_id,),
        ).fetchone()
    assert after == before


def test_ac_rwi_03_open_item_suppresses_next_window_with_one_typed_fact(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    revision = _revision()
    due = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
    runtime.register(tenant.tenant_id, revision, first_fire_at=due)
    first = runtime.scan(tenant.tenant_id)
    blocking_item_id = first.work_items[0].work_item_id

    next_due = datetime.now(UTC) - timedelta(seconds=1)
    _reset_trigger(tenant, revision, next_due)
    suppressed = runtime.scan(tenant.tenant_id)

    assert suppressed.work_items == ()
    assert len(suppressed.work_item_suppressions) == 1
    fact = suppressed.work_item_suppressions[0]
    assert fact.blocking_item_id == blocking_item_id
    assert fact.routine_ref == revision.routine_ref
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute(
            "SELECT count(*) FROM routine_work_item_suppressions WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
        assert count is not None and count[0] == 1

    _reset_trigger(tenant, revision, next_due)
    replay = runtime.scan(tenant.tenant_id)
    assert replay.work_item_suppressions == ()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute(
            "SELECT count(*) FROM routine_work_item_suppressions WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
        assert count is not None and count[0] == 1

    owner = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    receipt = runtime.complete_routine_work_item(
        owner,
        CompleteRoutineWorkItemCommand(UUID(int=10), blocking_item_id, "artifact:test-report"),
    )
    assert not isinstance(receipt, RecordProblem)
    following_due = datetime.now(UTC) - timedelta(seconds=1)
    _reset_trigger(tenant, revision, following_due)
    following = runtime.scan(tenant.tenant_id)
    assert len(following.work_items) == 1
    assert following.work_items[0].work_item_id != blocking_item_id


def test_ac_rwi_05_expired_open_item_raises_one_idempotent_alarm(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    revision = _revision()
    due = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
    runtime.register(tenant.tenant_id, revision, first_fire_at=due)
    item = runtime.scan(tenant.tenant_id).work_items[0]

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE inbox_work_items SET window_ends_at = transaction_timestamp() "
            "- interval '1 second' WHERE work_item_id = %s",
            (item.work_item_id,),
        )
        connection.commit()

    first_alarm = runtime.scan(tenant.tenant_id)
    assert len(first_alarm.work_item_alarms) == 1
    alarm = first_alarm.work_item_alarms[0]
    assert alarm.kind.value == "missed_window"
    assert alarm.work_item_id == item.work_item_id
    assert alarm.escalation_seat == "ctower-commander"
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute(
            "SELECT count(*) FROM routine_work_item_alarms WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
        assert count is not None and count[0] == 1

    replay = runtime.scan(tenant.tenant_id)
    assert replay.work_item_alarms == ()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute(
            "SELECT count(*) FROM routine_work_item_alarms WHERE tenant_id = %s",
            (tenant.tenant_id,),
        ).fetchone()
        assert count is not None and count[0] == 1


def test_ac_rwi_05_partial_gate_read_raises_one_degraded_alarm(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    revision = _revision()
    due = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=1)
    runtime.register(tenant.tenant_id, revision, first_fire_at=due)
    item = runtime.scan(tenant.tenant_id).work_items[0]

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE inbox_work_items SET gate_evidence = '{}'::jsonb WHERE work_item_id = %s",
            (item.work_item_id,),
        )
        connection.commit()

    first_alarm = runtime.scan(tenant.tenant_id)
    assert len(first_alarm.work_item_alarms) == 1
    assert first_alarm.work_item_alarms[0].kind.value == "degraded_read"
    assert first_alarm.work_item_alarms[0].work_item_id == item.work_item_id

    replay = runtime.scan(tenant.tenant_id)
    assert replay.work_item_alarms == ()


def test_ac_rwi_06_five_migrated_routines_fire_and_close_with_receipts(
    tenant: TenantFixture,
) -> None:
    revisions = {
        revision.routine_ref: revision
        for revision in load_routine_revisions(ROOT / "packs")
        if revision.routine_ref.startswith("mc-cron.")
    }
    assert set(revisions) == {
        "mc-cron.manibo-report@1",
        "mc-cron.structural-report@1",
        "mc-cron.manibo-merge-watch@1",
        "mc-cron.worktree-janitor-apply@1",
        "mc-cron.capacity-sentinel@1",
    }
    _create_open_ticket(tenant)

    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    now = datetime.now(UTC)
    for revision in revisions.values():
        runtime.register(tenant.tenant_id, revision, first_fire_at=_due_mark(revision, now))

    scan = runtime.scan(tenant.tenant_id)
    items = {item.routine_ref: item for item in scan.work_items}
    assert set(items) == set(revisions)
    assert all(item.gate_evidence.result == "fired" for item in items.values())

    manibo_id, _ = provision_seat(tenant, "manibo-commander")
    owner_ids = {
        "ctower-commander": tenant.commander_id,
        "manibo-commander": manibo_id,
    }
    receipts: dict[str, UUID] = {}
    for index, routine_ref in enumerate(sorted(items)):
        item = items[routine_ref]
        owner = Actor(owner_ids[item.owner_seat], tenant.tenant_id, PrincipalKind.COMMANDER)
        receipt = runtime.complete_routine_work_item(
            owner,
            CompleteRoutineWorkItemCommand(
                uuid4(), item.work_item_id, f"artifact:catch-parity/{item.routine_ref}"
            ),
        )
        assert not isinstance(receipt, RecordProblem), routine_ref
        assert receipt.work_item_id == item.work_item_id
        assert receipt.owner_seat == item.owner_seat
        receipts[routine_ref] = receipt.receipt_id
        print(
            f"catch-parity item={item.work_item_id} receipt={receipt.receipt_id} "
            f"routine={routine_ref} owner={item.owner_seat} sequence={index + 1}"
        )

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT item.routine_ref, item.status, item.receipt_artifact_ref,
                   receipt.receipt_id, receipt.work_item_id
            FROM inbox_work_items AS item
            JOIN routine_work_item_receipts AS receipt
              ON receipt.work_item_id = item.work_item_id
            WHERE item.tenant_id = %s
            ORDER BY item.routine_ref
            """,
            (tenant.tenant_id,),
        ).fetchall()
    assert len(rows) == len(revisions)
    assert {row[0] for row in rows} == set(revisions)
    assert all(row[1] == "closed" and row[2] for row in rows)
    assert {row[3] for row in rows} == set(receipts.values())
    assert all(row[4] == items[row[0]].work_item_id for row in rows)


def _revision() -> RoutineRevision:
    return RoutineRevision(
        routine_ref="mc-cron.test-report@1",
        revision_digest="sha256:" + "a" * 64,
        schedule_kind=ScheduleKind.MINUTE_HOUR_SET,
        timezone="UTC",
        local_time=None,
        concurrency=ConcurrencyPolicy.ALWAYS_ENQUEUE_BOUNDED,
        catch_up=CatchUpPolicy.SKIP_MISSED,
        catch_up_cap=1,
        handler_kind="routine_item",
        timeout_seconds=600,
        component_digests=("sha256:" + "b" * 64,),
        minute_marks=tuple(range(60)),
        hour_marks=None,
        routine_item=RoutineItemSpec(
            item_key="test-report",
            knowledge_ref="routine-test-report",
            document_id=UUID("00000000-0000-4000-8000-000000000001"),
            owner_seat="ctower-commander",
            escalation_seat="ctower-commander",
        ),
    )


def _reset_trigger(tenant: TenantFixture, revision: RoutineRevision, due: datetime) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE routine_triggers AS trigger SET next_fire_at = %s
            FROM routine_revisions AS stored
            WHERE trigger.revision_digest = stored.revision_digest
              AND trigger.tenant_id = %s AND stored.routine_ref = %s
            """,
            (due, tenant.tenant_id, revision.routine_ref),
        )
        connection.commit()


def _due_mark(revision: RoutineRevision, now: datetime) -> datetime:
    due = now.replace(second=0, microsecond=0)
    while due.minute not in revision.minute_marks:
        due -= timedelta(minutes=1)
    return due


def _create_open_ticket(tenant: TenantFixture) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        now = datetime.now(UTC)
        ticket_id = uuid4()
        connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, tenant_id, title, source_kind, source_ref, priority,
                custodian_principal_id, version, durability_state, created_by,
                created_at, project_key, current_episode
            ) VALUES (%s, %s, 'Catch parity gate ticket', 'acceptance', 'rwi-06', 'P1',
                      %s, 1, 'durability_pending', %s, %s, 'ctower', 1)
            """,
            (ticket_id, tenant.tenant_id, tenant.commander_id, tenant.operator_id, now),
        )
        connection.execute(
            """
            INSERT INTO lifecycle_episodes (ticket_id, tenant_id, episode_number, state, opened_at)
            VALUES (%s, %s, 1, 'open', %s)
            """,
            (ticket_id, tenant.tenant_id, now),
        )
        connection.commit()
