"""Project-scoped cursor query over canonical workflow transition facts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record.interface import RecordProblem
from ctower_kernel.record.movement_events import (
    MovementCountList,
    MovementCountRow,
    MovementEvent,
    MovementEventPage,
)
from ctower_kernel.record.transaction import project_scope_refusal
from ctower_kernel.record.workflow_validation import workflow_payload_for_read

if TYPE_CHECKING:
    from ctower_kernel.record.interface import Actor

__all__: tuple[str, ...] = ()
MAX_PAGE_SIZE = 100


def movement_events(
    dsn: str,
    actor: Actor,
    project_key: str,
    *,
    cursor: int,
    limit: int,
) -> MovementEventPage | RecordProblem:
    """Read one project's workflow transition facts as a record-position page.

    Only accepted `workflow.changed` transition events count as movement; start
    and resolve_close operations are not movement facts.  The page is derived
    from the same canonical project event stream (never a second ledger).
    """

    if cursor < 0 or limit < 1 or limit > MAX_PAGE_SIZE:
        return RecordProblem(
            "validation-error", "Invalid movement page cursor", 422, "Invalid movement page cursor"
        )
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
            SELECT event.event_id, event.record_position, event.server_time,
                event.kind, event.payload, event.stream_id
            FROM event_links AS link
            JOIN events AS event
              ON event.event_id = link.event_id AND event.tenant_id = link.tenant_id
            JOIN tickets AS ticket
              ON ticket.tenant_id = link.tenant_id AND ticket.ticket_id = link.subject_id
            WHERE link.tenant_id = %s AND link.subject_kind = 'ticket'
              AND ticket.project_key = %s
              AND event.kind = 'workflow.changed'
              AND event.payload->>'operation' = 'transition'
              AND event.record_position > %s
            ORDER BY event.record_position
            LIMIT %s
            """,
            (actor.tenant_id, project_key, cursor, limit + 1),
        ).fetchall()
    page_rows = rows[:limit]
    events = tuple(_event(row) for row in page_rows)
    next_cursor = events[-1].record_position if len(rows) > limit and events else None
    return MovementEventPage(project_key=project_key, events=events, next_cursor=next_cursor)


def movement_counts(
    dsn: str,
    actor: Actor,
    *,
    now: datetime,
) -> MovementCountList | RecordProblem:
    """Read every tenant transition fact plus the ledger watermark.

    The digest is operator-only, so the scope is the whole tenant; the kernel
    fold windows the rows to the prior Europe/Vilnius civil day.  This is the
    same canonical event stream — never a second ledger.
    """

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        watermark_row = connection.execute(
            "SELECT last_position FROM record_position_ledger WHERE singleton"
        ).fetchone()
        watermark = 0 if watermark_row is None else int(cast(int, watermark_row["last_position"]))
        rows = connection.execute(
            """
            SELECT ticket.project_key, event.payload, event.server_time
            FROM event_links AS link
            JOIN events AS event
              ON event.event_id = link.event_id AND event.tenant_id = link.tenant_id
            JOIN tickets AS ticket
              ON ticket.tenant_id = link.tenant_id AND ticket.ticket_id = link.subject_id
            WHERE link.tenant_id = %s AND link.subject_kind = 'ticket'
              AND event.kind = 'workflow.changed'
              AND event.payload->>'operation' = 'transition'
            """,
            (actor.tenant_id,),
        ).fetchall()
    return MovementCountList(
        rows=tuple(_count_row(row) for row in rows),
        watermark=watermark,
        observed_at=now,
    )


def _count_row(row: dict[str, object]) -> MovementCountRow:
    payload = workflow_payload_for_read(cast(dict[str, object], row["payload"]))
    return MovementCountRow(
        project_key=str(row["project_key"]),
        source_stage=str(payload.get("source_stage", "")),
        stage=str(payload.get("stage", "")),
        occurred_at=cast(datetime, row["server_time"]),
    )


def _event(row: dict[str, object]) -> MovementEvent:
    payload = workflow_payload_for_read(cast(dict[str, object], row["payload"]))
    return MovementEvent(
        event_id=cast(UUID, row["event_id"]),
        record_position=int(cast(int, row["record_position"])),
        ticket_id=UUID(str(payload["ticket_id"])),
        from_stage=str(payload.get("source_stage", "")),
        to_stage=str(payload.get("stage", "")),
        evaluation_ref=str(payload.get("evaluation_ref", "")),
        workflow_ref=str(payload.get("workflow_ref", "")),
        workflow_version=int(cast(int, payload.get("workflow_version", 0))),
        occurred_at=cast(datetime, row["server_time"]),
    )
