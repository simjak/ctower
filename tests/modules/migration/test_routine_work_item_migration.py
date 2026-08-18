"""Migration regression for routine work-item event constraints."""

from __future__ import annotations

import psycopg

from ._postgres import Database

__all__: tuple[str, ...] = ()


def test_final_schema_retains_routine_work_item_event_kinds(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'events'::regclass AND conname = 'events_kind_check'"
        ).fetchone()
    assert row is not None
    definition = str(row[0])
    assert all(
        f"'{kind}'" in definition
        for kind in (
            "routine.work_item_appended",
            "routine.work_item_suppressed",
            "routine.work_item_completed",
            "routine.work_item_alarm_raised",
        )
    )
