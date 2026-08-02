"""Accepted project event feed with SQL-first scope and bound cursors."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record._project_event_payload import project_event_payload_from_mapping
from ctower_kernel.record.events import (
    EventKind,
    project_event_kinds,
    project_event_kinds_by_scope,
)
from ctower_kernel.record.interface import (
    Actor,
    ProjectEvent,
    ProjectEventCursor,
    ProjectEventPage,
    RecordProblem,
)

__all__: tuple[str, ...] = ()
MAX_PAGE_SIZE = 100


def project_events(
    dsn: str,
    actor: Actor,
    project_key: str,
    cursor: ProjectEventCursor,
    *,
    limit: int,
) -> ProjectEventPage | RecordProblem:
    if cursor.project_key != project_key:
        return RecordProblem(
            "project-scope-denied",
            "Project event cursor is bound to another project",
            404,
            "Project feed unavailable",
        )
    if limit < 1 or limit > MAX_PAGE_SIZE:
        return RecordProblem(
            "validation-error",
            "Project event page limit must be between 1 and 100",
            422,
            "Invalid project event page",
        )
    kinds = [kind.value for kind in project_event_kinds()]
    aggregate_kinds = [kind.value for kind in project_event_kinds_by_scope("aggregate-ticket")]
    linked_kinds = [kind.value for kind in project_event_kinds_by_scope("linked-ticket")]
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as connection:
        connection.execute("SET ROLE ctower_svc")
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            watermark_row = connection.execute(
                """
                SELECT COALESCE(MAX(confirmation.acceptance_position), 0) AS value
                FROM events AS event
                LEFT JOIN event_links AS link
                  ON link.tenant_id = event.tenant_id
                 AND link.event_id = event.event_id
                 AND link.subject_kind = 'ticket'
                 AND event.kind = ANY(%s)
                JOIN tickets AS ticket
                  ON ticket.tenant_id = event.tenant_id
                 AND ticket.ticket_id = CASE
                   WHEN event.kind = ANY(%s) THEN event.aggregate_id
                   ELSE link.subject_id
                 END
                JOIN durability_acceptance_confirmations AS confirmation
                  ON confirmation.tenant_id = event.tenant_id
                 AND confirmation.principal_id = event.actor_principal_id
                 AND confirmation.client_command_id = event.client_command_id
                WHERE event.tenant_id = %s AND ticket.project_key = %s
                  AND event.kind = ANY(%s)
                """,
                (linked_kinds, aggregate_kinds, actor.tenant_id, project_key, kinds),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT event.event_id, event.record_position, event.stream_id, event.sequence,
                    event.kind, event.aggregate_id, event.actor_principal_id,
                    event.client_command_id, event.server_time, event.payload,
                    confirmation.acceptance_position, ticket.project_key
                FROM events AS event
                LEFT JOIN event_links AS link
                  ON link.tenant_id = event.tenant_id
                 AND link.event_id = event.event_id
                 AND link.subject_kind = 'ticket'
                 AND event.kind = ANY(%s)
                JOIN tickets AS ticket
                  ON ticket.tenant_id = event.tenant_id
                 AND ticket.ticket_id = CASE
                   WHEN event.kind = ANY(%s) THEN event.aggregate_id
                   ELSE link.subject_id
                 END
                JOIN durability_acceptance_confirmations AS confirmation
                  ON confirmation.tenant_id = event.tenant_id
                 AND confirmation.principal_id = event.actor_principal_id
                 AND confirmation.client_command_id = event.client_command_id
                WHERE event.tenant_id = %s AND ticket.project_key = %s
                  AND event.kind = ANY(%s)
                  AND (
                    confirmation.acceptance_position > %s
                    OR (
                      confirmation.acceptance_position = %s
                      AND event.record_position > %s
                    )
                  )
                ORDER BY confirmation.acceptance_position, event.record_position
                LIMIT %s
                """,
                (
                    linked_kinds,
                    aggregate_kinds,
                    actor.tenant_id,
                    project_key,
                    kinds,
                    cursor.acceptance_position,
                    cursor.acceptance_position,
                    cursor.record_position,
                    limit + 1,
                ),
            ).fetchall()
    page_rows = rows[:limit]
    events = tuple(_event(row) for row in page_rows)
    next_cursor = (
        ProjectEventCursor(
            project_key,
            events[-1].acceptance_position,
            events[-1].record_position,
        )
        if events
        else cursor
    )
    watermark = int(cast(int, watermark_row["value"])) if watermark_row is not None else 0
    return ProjectEventPage(
        project_key=project_key,
        events=events,
        next_cursor=next_cursor,
        has_more=len(rows) > limit,
        source_watermark=watermark,
    )


def _event(row: dict[str, object]) -> ProjectEvent:
    kind = EventKind(str(row["kind"]))
    project_key = str(row["project_key"])
    payload = project_event_payload_from_mapping(
        kind,
        cast(dict[str, object], row["payload"]),
        legacy_project_key=project_key,
    )
    return ProjectEvent(
        acceptance_position=int(cast(int, row["acceptance_position"])),
        actor_principal_id=cast(UUID, row["actor_principal_id"]),
        aggregate_id=cast(UUID, row["aggregate_id"]),
        client_command_id=cast(UUID, row["client_command_id"]),
        event_id=cast(UUID, row["event_id"]),
        kind=kind,
        occurred_at=cast(datetime, row["server_time"]),
        payload=payload,
        record_position=int(cast(int, row["record_position"])),
        sequence=int(cast(int, row["sequence"])),
        stream_id=str(row["stream_id"]),
    )
