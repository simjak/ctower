"""Shared real-PostgreSQL apparatus for the Routine work-item acceptance suites."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
from support.tenant_fixture import TenantFixture

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    RoutineRevision,
    ScheduleKind,
)
from ctower_kernel.runtime.items import RoutineItemSpec

__all__ = [
    "append_movement_event",
    "close_window",
    "expire_window",
    "past_minute_mark",
    "read_alarm_rows",
    "reset_trigger",
    "revision",
    "single_mark_revision",
]

TEST_DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000001")


def revision(
    *,
    minute_marks: tuple[int, ...] = tuple(range(60)),
    escalation_seat: str = "ctower-commander",
    digest_seed: str = "a",
) -> RoutineRevision:
    """Build the acceptance Routine revision that fires one pointer-only item."""

    return RoutineRevision(
        routine_ref="mc-cron.test-report@1",
        revision_digest="sha256:" + digest_seed * 64,
        schedule_kind=ScheduleKind.MINUTE_HOUR_SET,
        timezone="UTC",
        local_time=None,
        concurrency=ConcurrencyPolicy.ALWAYS_ENQUEUE_BOUNDED,
        catch_up=CatchUpPolicy.SKIP_MISSED,
        catch_up_cap=1,
        handler_kind="routine_item",
        timeout_seconds=600,
        component_digests=("sha256:" + "b" * 64,),
        minute_marks=minute_marks,
        hour_marks=None,
        routine_item=RoutineItemSpec(
            item_key="test-report",
            knowledge_ref="routine-test-report",
            document_id=TEST_DOCUMENT_ID,
            owner_seat="ctower-commander",
            escalation_seat=escalation_seat,
        ),
    )


def past_minute_mark(minutes_ago: int = 1) -> datetime:
    """Return a whole-minute instant strictly in the past."""

    return datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=minutes_ago)


def single_mark_revision(
    due: datetime, *, escalation_seat: str = "ctower-commander"
) -> RoutineRevision:
    """Pin the only due mark to ``due`` so the queued window can never be `now`.

    AC-RWI-05 expiry must be derived from the item's own row. A revision that
    marks every minute lets catch-up queue the current minute boundary, which
    can be less than a second old, so any wall-clock expiry races migration
    0079's ``window_ends_at > scheduled_for`` check.
    """

    return revision(minute_marks=(due.minute,), escalation_seat=escalation_seat)


def reset_trigger(tenant: TenantFixture, routine_ref: str, due: datetime) -> None:
    """Re-arm the registered trigger so the next scan sees a due window."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE routine_triggers AS trigger SET next_fire_at = %s
            FROM routine_revisions AS stored
            WHERE trigger.revision_digest = stored.revision_digest
              AND trigger.tenant_id = %s AND stored.routine_ref = %s
            """,
            (due, tenant.tenant_id, routine_ref),
        )
        connection.commit()


def expire_window(tenant: TenantFixture, work_item_id: UUID, *, seconds: int = 1) -> datetime:
    """End the window from the row's own `scheduled_for`, never from wall time."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            UPDATE inbox_work_items
            SET window_ends_at = scheduled_for + make_interval(secs => %s)
            WHERE work_item_id = %s
            RETURNING window_ends_at
            """,
            (seconds, work_item_id),
        ).fetchone()
        connection.commit()
    assert row is not None
    ended: datetime = row[0]
    return ended


def close_window(tenant: TenantFixture, work_item_id: UUID, ends_at: datetime) -> None:
    """Place the window boundary at an exact instant supplied by the caller."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(
            "UPDATE inbox_work_items SET window_ends_at = %s WHERE work_item_id = %s",
            (ends_at, work_item_id),
        )
        connection.commit()


def read_alarm_rows(tenant: TenantFixture) -> list[tuple[str, str | None]]:
    """Read every recorded observation as (kind, unresolved_reason)."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT kind, unresolved_reason FROM routine_work_item_alarms
            WHERE tenant_id = %s ORDER BY recorded_at, alarm_id
            """,
            (tenant.tenant_id,),
        ).fetchall()
    return [(str(row[0]), None if row[1] is None else str(row[1])) for row in rows]


def append_movement_event(tenant: TenantFixture) -> None:
    """Land one extra recorded event so a movement gate observes real movement."""

    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT stream_id, aggregate_id, sequence, request_sha256, prev_hash, event_hash
            FROM events WHERE tenant_id = %s ORDER BY record_position DESC LIMIT 1
            """,
            (tenant.tenant_id,),
        ).fetchone()
        assert row is not None, "a movement gate needs at least one baseline event"
        position = connection.execute(
            "UPDATE record_position_ledger SET last_position = last_position + 1 "
            "WHERE singleton RETURNING last_position"
        ).fetchone()
        assert position is not None
        connection.execute(
            """
            INSERT INTO events (
                event_id, tenant_id, stream_id, aggregate_id, sequence, kind,
                schema_version, actor_principal_id, client_command_id, request_sha256,
                correlation_id, causation_id, origin, server_time, payload,
                prev_hash, event_hash, record_position
            ) VALUES (%s, %s, %s, %s, %s, 'ticket.comment_added', 1, %s, %s, %s,
                      %s, NULL, 'api', %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                tenant.tenant_id,
                row[0],
                row[1],
                int(row[2]) + 1,
                tenant.operator_id,
                uuid4(),
                row[3],
                uuid4(),
                datetime.now(UTC),
                json.dumps({"schema": "ctower.event/v1"}),
                row[5],
                hashlib.sha256(uuid4().bytes).digest(),
                position[0],
            ),
        )
        connection.commit()
