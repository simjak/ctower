"""Project-scoped cursor query over catalog-derived typed events."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, AuditEvent, RecordProblem
from ctower_kernel.record.events import EventKind, project_event_kinds
from ctower_kernel.record.project_events import ProjectEventPage
from ctower_kernel.record.transaction import project_scope_refusal

__all__: tuple[str, ...] = ()
MAX_PAGE_SIZE = 100


def project_events(
    dsn: str,
    actor: Actor,
    project_key: str,
    *,
    cursor: int,
    limit: int,
) -> ProjectEventPage | RecordProblem:
    """Read one project's catalog-derived feed events as a record-position cursor page."""

    if cursor < 0 or limit < 1 or limit > MAX_PAGE_SIZE:
        return RecordProblem(
            "validation-error", "Invalid event page cursor", 422, "Invalid event page cursor"
        )
    kinds = [kind.value for kind in project_event_kinds()]
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        refusal = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(project_key,),
        )
        if refusal is not None:
            return refusal
        rows = connection.execute(
            """
            SELECT event.event_id, event.record_position, event.stream_id, event.sequence,
                event.kind, event.actor_principal_id, event.client_command_id,
                event.server_time, event.payload, event.event_hash
            FROM event_links AS link
            JOIN events AS event
              ON event.event_id = link.event_id AND event.tenant_id = link.tenant_id
            JOIN tickets AS ticket
              ON ticket.tenant_id = link.tenant_id AND ticket.ticket_id = link.subject_id
            WHERE link.tenant_id = %s AND link.subject_kind = 'ticket'
              AND ticket.project_key = %s AND event.kind = ANY(%s)
              AND event.record_position > %s
            ORDER BY event.record_position
            LIMIT %s
            """,
            (actor.tenant_id, project_key, kinds, cursor, limit + 1),
        ).fetchall()
    page_rows = rows[:limit]
    events = tuple(_event(row) for row in page_rows)
    next_cursor = events[-1].record_position if len(rows) > limit and events else None
    return ProjectEventPage(project_key=project_key, events=events, next_cursor=next_cursor)


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
