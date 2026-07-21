"""Tenant-safe cursor audit query over typed event subject links."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, AuditEvent, AuditPage, RecordProblem
from ctower_kernel.record.events import EventKind

__all__: tuple[str, ...] = ()
MAX_PAGE_SIZE = 100


def ticket_audit(
    dsn: str,
    actor: Actor,
    ticket_id: UUID,
    *,
    cursor: int,
    limit: int,
) -> AuditPage | RecordProblem:
    if cursor < 0 or limit < 1 or limit > MAX_PAGE_SIZE:
        return RecordProblem(
            "validation-error", "Invalid audit cursor", 422, "Invalid audit cursor"
        )
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        exists = connection.execute(
            "SELECT 1 FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
            (actor.tenant_id, ticket_id),
        ).fetchone()
        if exists is None:
            return RecordProblem(
                "tenant-scope-denied", "Ticket unavailable", 404, "Ticket unavailable"
            )
        rows = connection.execute(
            """
            SELECT event.event_id, event.record_position, event.stream_id, event.sequence,
                event.kind, event.actor_principal_id, event.client_command_id,
                event.server_time, event.payload, event.event_hash
            FROM event_links AS link
            JOIN events AS event
              ON event.event_id = link.event_id AND event.tenant_id = link.tenant_id
            WHERE link.tenant_id = %s AND link.subject_kind = 'ticket'
              AND link.subject_id = %s AND event.record_position > %s
            ORDER BY event.record_position
            LIMIT %s
            """,
            (actor.tenant_id, ticket_id, cursor, limit + 1),
        ).fetchall()
    page_rows = rows[:limit]
    events = tuple(_event(row) for row in page_rows)
    next_cursor = events[-1].record_position if len(rows) > limit and events else None
    return AuditPage(ticket_id=ticket_id, events=events, next_cursor=next_cursor)


def _event(row: dict[str, object]) -> AuditEvent:
    return AuditEvent(
        actor_principal_id=cast(UUID, row["actor_principal_id"]),
        command_id=cast(UUID, row["client_command_id"]),
        event_hash=f"sha256:{bytes(cast(bytes, row['event_hash'])).hex()}",
        event_id=cast(UUID, row["event_id"]),
        kind=EventKind(str(row["kind"])),
        occurred_at=cast(datetime, row["server_time"]),
        payload=cast(dict[str, object], row["payload"]),
        record_position=int(cast(int, row["record_position"])),
        sequence=int(cast(int, row["sequence"])),
        stream_id=str(row["stream_id"]),
    )
