"""Test-only PostgreSQL fault injector below the projection acceptance Interface."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal, cast
from uuid import UUID

import psycopg

__all__ = ["InjectedOutboxFailure", "ProjectionFault", "ProjectionFaults"]

InjectedOutboxFailure = psycopg.errors.RaiseException
type ProjectionFault = Literal["behind", "ahead", "gap", "unknown-event"]


class ProjectionFaults:
    """Construct disposable projection and Record-source faults for Interface tests."""

    def __init__(self, admin_dsn: str) -> None:
        self._admin_dsn = admin_dsn

    def remove_projected_card(self, tenant_id: UUID, ticket_id: UUID) -> None:
        with psycopg.connect(self._admin_dsn) as connection:
            connection.execute(
                "DELETE FROM board_projection_rows WHERE tenant_id = %s AND ticket_id = %s",
                (tenant_id, ticket_id),
            )

    @contextmanager
    def reject_outbox_appends(self) -> Iterator[None]:
        with psycopg.connect(self._admin_dsn) as connection:
            connection.execute(
                """
                CREATE FUNCTION ctower_test_reject_projection_outbox()
                    RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'injected projection outbox failure';
                END
                $$;
                CREATE TRIGGER ctower_test_reject_projection_outbox
                    BEFORE INSERT ON outbox
                    FOR EACH ROW EXECUTE FUNCTION ctower_test_reject_projection_outbox();
                """
            )
        try:
            yield
        finally:
            with psycopg.connect(self._admin_dsn) as connection:
                connection.execute("DROP TRIGGER ctower_test_reject_projection_outbox ON outbox")
                connection.execute("DROP FUNCTION ctower_test_reject_projection_outbox()")

    def record_positions(self) -> tuple[int, ...]:
        with psycopg.connect(self._admin_dsn) as connection:
            rows = connection.execute(
                "SELECT record_position FROM events ORDER BY record_position"
            ).fetchall()
        return tuple(int(cast(int, row[0])) for row in rows)

    def inject_source_fault(
        self, tenant_id: UUID, source_watermark: int, fault: ProjectionFault
    ) -> None:
        if fault == "behind":
            return
        with psycopg.connect(self._admin_dsn) as connection:
            if fault == "ahead":
                connection.execute(
                    """
                    UPDATE outbox_consumer_cursors SET acceptance_position = %s
                    WHERE consumer_key = 'board_projection' AND tenant_id = %s
                      AND topic = 'record.events'
                    """,
                    (source_watermark + 1, tenant_id),
                )
            elif fault == "gap":
                connection.execute(
                    """
                    UPDATE events SET record_position = record_position + 1
                    WHERE record_position = %s
                    """,
                    (source_watermark,),
                )
            else:
                connection.execute("ALTER TABLE events DROP CONSTRAINT events_kind_check")
                connection.execute(
                    "UPDATE events SET kind = 'future.changed' WHERE record_position = %s",
                    (source_watermark,),
                )
