"""AC-RWI-01..04/06: Routine work items over real PostgreSQL."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from support.routine_items import (
    TEST_DOCUMENT_ID,
    past_minute_mark,
    reset_trigger,
    revision,
)
from support.tenant_fixture import TenantFixture, provision_seat

from ctower_api.control_worker import load_routine_revisions
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.runtime import Routine, RoutineRevision
from ctower_kernel.runtime.gates import ActivityGate
from ctower_kernel.runtime.items import CompleteRoutineWorkItemCommand
from ctower_kernel.runtime.postgres import PostgresRuntime

ROOT = Path(__file__).parents[3]
ROUTINE_REF = "mc-cron.test-report@1"
__all__: tuple[str, ...] = ()


def test_ac_rwi_01_fire_appends_one_pointer_only_inbox_item_and_replays_zero(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    due = past_minute_mark()
    runtime.register(tenant.tenant_id, revision(), first_fire_at=due)

    first = runtime.scan(tenant.tenant_id)
    assert [item.routine_ref for item in first.work_items] == [ROUTINE_REF]
    item = first.work_items[0]
    assert item.owner_seat == "ctower-commander"
    assert item.knowledge_ref == "routine-test-report"
    assert item.document_id == TEST_DOCUMENT_ID
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
        assert columns[0] == ROUTINE_REF
        assert columns[1] == "ctower-commander"
        assert columns[2] == "routine-test-report"
        assert columns[3] == TEST_DOCUMENT_ID
        assert columns[4]["result"] == "fired"
        assert "prompt" not in columns[5] and "instructions" not in columns[5]

    reset_trigger(tenant, ROUTINE_REF, due)
    replay = runtime.scan(tenant.tenant_id)
    assert replay.work_items == ()
    assert replay.session_writes == ()


def test_ac_rwi_04_completion_requires_owner_receipt_and_is_idempotent(
    tenant: TenantFixture,
) -> None:
    runtime = PostgresRuntime(tenant.database.runtime_dsn)
    runtime.register(tenant.tenant_id, revision(), first_fire_at=past_minute_mark())
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

    before = _item_row(tenant, item.work_item_id)
    double = runtime.complete_routine_work_item(
        owner,
        CompleteRoutineWorkItemCommand(UUID(int=3), item.work_item_id, "artifact:other"),
    )
    assert isinstance(double, RecordProblem)
    assert _item_row(tenant, item.work_item_id) == before


def test_ac_rwi_04_refusal_matrix_records_each_refusal_with_zero_mutation(
    tenant: TenantFixture,
) -> None:
    """Missing reference, foreign seat, and double closure each refuse and mutate nothing."""

    runtime = PostgresRuntime(tenant.database.runtime_dsn)
    runtime.register(tenant.tenant_id, revision(), first_fire_at=past_minute_mark())
    item = runtime.scan(tenant.tenant_id).work_items[0]
    owner = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    foreign_id, _ = provision_seat(tenant, "foreign-commander")
    foreign = Actor(foreign_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    opened = _item_row(tenant, item.work_item_id)

    absent = runtime.complete_routine_work_item(
        owner, CompleteRoutineWorkItemCommand(uuid4(), uuid4(), "artifact:absent")
    )
    no_artifact = runtime.complete_routine_work_item(
        owner, CompleteRoutineWorkItemCommand(uuid4(), item.work_item_id, "")
    )
    trespass = runtime.complete_routine_work_item(
        foreign, CompleteRoutineWorkItemCommand(uuid4(), item.work_item_id, "artifact:foreign")
    )
    assert _item_row(tenant, item.work_item_id) == opened

    accepted = runtime.complete_routine_work_item(
        owner, CompleteRoutineWorkItemCommand(uuid4(), item.work_item_id, "artifact:owner")
    )
    assert not isinstance(accepted, RecordProblem)
    closed = _item_row(tenant, item.work_item_id)
    reclosed = runtime.complete_routine_work_item(
        owner, CompleteRoutineWorkItemCommand(uuid4(), item.work_item_id, "artifact:again")
    )

    refusals = [absent, no_artifact, trespass, reclosed]
    assert all(isinstance(problem, RecordProblem) for problem in refusals)
    assert [problem.code for problem in refusals if isinstance(problem, RecordProblem)] == [
        "routine-work-item-not-found",
        "routine-work-item-artifact-required",
        "routine-work-item-forbidden",
        "routine-work-item-already-completed",
    ]
    assert _item_row(tenant, item.work_item_id) == closed
    assert _receipt_count(tenant) == 1
    assert _refused_codes(tenant) == {
        "routine-work-item-not-found",
        "routine-work-item-artifact-required",
        "routine-work-item-forbidden",
        "routine-work-item-already-completed",
    }


def test_ac_rwi_03_open_item_suppresses_next_window_with_one_typed_fact(
    tenant: TenantFixture,
) -> None:
    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    runtime.register(tenant.tenant_id, revision(), first_fire_at=past_minute_mark())
    first = runtime.scan(tenant.tenant_id)
    blocking_item_id = first.work_items[0].work_item_id

    next_due = datetime.now(UTC) - timedelta(seconds=1)
    reset_trigger(tenant, ROUTINE_REF, next_due)
    suppressed = runtime.scan(tenant.tenant_id)

    assert suppressed.work_items == ()
    assert len(suppressed.work_item_suppressions) == 1
    fact = suppressed.work_item_suppressions[0]
    assert fact.blocking_item_id == blocking_item_id
    assert fact.routine_ref == ROUTINE_REF
    assert _suppression_count(tenant) == 1

    reset_trigger(tenant, ROUTINE_REF, next_due)
    replay = runtime.scan(tenant.tenant_id)
    assert replay.work_item_suppressions == ()
    assert _suppression_count(tenant) == 1

    owner = Actor(tenant.commander_id, tenant.tenant_id, PrincipalKind.COMMANDER)
    receipt = runtime.complete_routine_work_item(
        owner,
        CompleteRoutineWorkItemCommand(UUID(int=10), blocking_item_id, "artifact:test-report"),
    )
    assert not isinstance(receipt, RecordProblem)
    following_due = datetime.now(UTC) - timedelta(seconds=1)
    reset_trigger(tenant, ROUTINE_REF, following_due)
    following = runtime.scan(tenant.tenant_id)
    assert len(following.work_items) == 1
    assert following.work_items[0].work_item_id != blocking_item_id


def test_ac_rwi_03_suppression_is_unconditional_across_the_gate_set(
    tenant: TenantFixture,
) -> None:
    """AC-RWI-03 has no gate exemption: a movement-gated fire is suppressed the same way."""

    runtime = Routine(PostgresRuntime(tenant.database.runtime_dsn))
    gated = replace(
        revision(digest_seed="d"),
        activity_gate=ActivityGate(
            kind="new_movement_since_watermark", source="events", threshold=None, project_key=None
        ),
    )
    runtime.register(tenant.tenant_id, gated, first_fire_at=past_minute_mark())
    first = runtime.scan(tenant.tenant_id)
    assert len(first.work_items) == 1
    blocking_item_id = first.work_items[0].work_item_id

    reset_trigger(tenant, ROUTINE_REF, datetime.now(UTC) - timedelta(seconds=1))
    suppressed = runtime.scan(tenant.tenant_id)

    assert suppressed.work_items == ()
    assert [fact.blocking_item_id for fact in suppressed.work_item_suppressions] == [
        blocking_item_id
    ]
    assert _suppression_count(tenant) == 1


def test_ac_rwi_06_five_migrated_routines_fire_and_close_with_receipts(
    tenant: TenantFixture,
) -> None:
    revisions = {
        item.routine_ref: item
        for item in load_routine_revisions(ROOT / "packs")
        if item.routine_ref.startswith("mc-cron.")
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
    for item_revision in revisions.values():
        runtime.register(
            tenant.tenant_id, item_revision, first_fire_at=_due_mark(item_revision, now)
        )

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


def _item_row(tenant: TenantFixture, work_item_id: UUID) -> tuple[object, ...] | None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT status, receipt_id, receipt_artifact_ref FROM inbox_work_items "
            "WHERE work_item_id = %s",
            (work_item_id,),
        ).fetchone()
    return None if row is None else tuple(row)


def _receipt_count(tenant: TenantFixture) -> int:
    return _count(tenant, "routine_work_item_receipts")


def _suppression_count(tenant: TenantFixture) -> int:
    return _count(tenant, "routine_work_item_suppressions")


def _count(tenant: TenantFixture, table: str) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            f"SELECT count(*) FROM {table} WHERE tenant_id = %s",  # noqa: S608
            (tenant.tenant_id,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _refused_codes(tenant: TenantFixture) -> set[str]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT response_body ->> 'code' FROM command_results
            WHERE tenant_id = %s AND status_code >= 400
            """,
            (tenant.tenant_id,),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _due_mark(item_revision: RoutineRevision, now: datetime) -> datetime:
    due = now.replace(second=0, microsecond=0)
    while due.minute not in item_revision.minute_marks:
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
