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


def test_final_schema_persists_exact_knowledge_document_pins(
    migration_database: Database,
) -> None:
    with psycopg.connect(migration_database.admin_dsn) as connection:
        rows = connection.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_name IN ('routine_item_specs', 'inbox_work_items')
              AND column_name = 'document_id'
            ORDER BY table_name
            """
        ).fetchall()
    assert rows == [
        ("inbox_work_items", "document_id"),
        ("routine_item_specs", "document_id"),
    ]
