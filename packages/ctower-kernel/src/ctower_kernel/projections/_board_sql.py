"""Disposable Board row fold and read mechanics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from ctower_kernel.projections import (
    BoardCard,
    BoardDeliverySurfaceAvailability,
    BoardDeliverySurfaceState,
    BoardLane,
    BoardQuery,
    BoardView,
    ProjectionHealth,
)
from ctower_kernel.projections import _board_context_sql as _context
from ctower_kernel.projections.interface import (
    AppliedLabel,
    ChangeReference,
    HumanWaiting,
    HumanWaitingState,
    TenantDisplayIdentity,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.transaction import project_scope_refusal

__all__: tuple[str, ...] = ()

_NOT_WAITING = HumanWaiting(HumanWaitingState.NOT_WAITING)
_NO_QUALIFYING_CHECKPOINT = BoardDeliverySurfaceAvailability(
    BoardDeliverySurfaceState.NO_QUALIFYING_CHECKPOINT
)


@dataclass(frozen=True, slots=True)
class _ContextSets:
    tenant_display_identity: TenantDisplayIdentity
    change_references: dict[UUID, tuple[ChangeReference, ...]]
    applied_labels: dict[UUID, tuple[AppliedLabel, ...]]
    human_waiting: dict[UUID, HumanWaiting]
    delivery_surface: dict[UUID, BoardDeliverySurfaceAvailability]
    inbox_threads: dict[UUID, tuple[UUID, ...]]


_FoldHandler = Callable[
    [psycopg.Connection[dict[str, object]], UUID, dict[str, object], dict[str, object], int],
    None,
]


def apply_message(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
) -> None:
    handler = _FOLD_DISPATCH.get(EventKind(str(message["kind"])))
    if handler is None:
        return
    payload = cast(dict[str, object], message["event_payload"])
    position = int(cast(int, message["acceptance_position"]))
    handler(connection, tenant_id, message, payload, position)


def read_view(
    dsn: str, actor: Actor, query: BoardQuery, *, source: int
) -> BoardView | RecordProblem:
    """Read one authenticated Project-scoped Board view."""

    return _read_view(dsn, actor=actor, query=query, source=source)


def _read_view_for_catch_up(dsn: str, tenant_id: UUID, *, source: int) -> BoardView:
    """Read the tenant projection after an internal accepted-outbox catch-up."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        return _read_view_data(connection, tenant_id, None, source=source)


def _read_view(
    dsn: str, actor: Actor, query: BoardQuery, *, source: int
) -> BoardView | RecordProblem:
    """Read one Board view after composing the authenticated scope predicate."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        refusal = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(query.project_key,),
            allow_operator_read=True,
        )
        if refusal is not None:
            return refusal
        return _read_view_data(connection, actor.tenant_id, query, source=source)


def portfolio_board(dsn: str, actor: Actor, *, source: int) -> BoardView | RecordProblem:
    """Read every Project's cards at once, refusing every non-operator principal.

    The requested Project set is empty here by construction, so this is the one read
    that asks the chokepoint for persisted operator authority rather than for grants
    over named Projects.
    """

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        refusal = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(),
            operator_only=True,
            allow_operator_read=True,
        )
        if refusal is not None:
            return refusal
        return _read_view_data(connection, actor.tenant_id, None, source=source)


def _read_view_data(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    query: BoardQuery | None,
    *,
    source: int,
) -> BoardView:
    project_key, source_kind, source_ref = _query_filters(query)
    cursor = connection.execute(
        """
        SELECT acceptance_position, health, blocked_outbox_id
        FROM outbox_consumer_cursors
        WHERE consumer_key = 'board_projection' AND tenant_id = %s
          AND topic = 'record.events'
        """,
        (tenant_id,),
    ).fetchone()
    row_count = connection.execute(
        """
        SELECT count(*) AS value
        FROM board_projection_rows
        WHERE tenant_id = %s
          AND (%s::text IS NULL OR project_key = %s)
        """,
        (tenant_id, project_key, project_key),
    ).fetchone()
    rows = connection.execute(
        """
        SELECT * FROM board_projection_rows
        WHERE tenant_id = %s
          AND (%s::text IS NULL OR project_key = %s)
          AND (%s::text IS NULL OR source_kind = %s)
          AND (%s::text IS NULL OR source_ref = %s)
        ORDER BY ticket_id
        """,
        (
            tenant_id,
            project_key,
            project_key,
            source_kind,
            source_kind,
            source_ref,
            source_ref,
        ),
    ).fetchall()
    expected_cards = _expected_card_count(connection, tenant_id, project_key)
    scoped_source = _project_source(connection, tenant_id, project_key)
    scoped_projection = _scoped_projection_position(connection, tenant_id, project_key)
    context = _read_context_sets(connection, tenant_id, rows)
    global_projection = _cursor_position(cursor)
    view_source, projection = _scoped_watermarks(
        project_key,
        source=source,
        scoped_source=scoped_source,
        global_projection=global_projection,
        scoped_projection=scoped_projection,
    )
    actual_cards = int(cast(int, row_count["value"])) if row_count else 0
    current = _is_current(
        cursor,
        global_projection=global_projection,
        source=source,
        projection=projection,
        view_source=view_source,
        actual_cards=actual_cards,
        expected_cards=expected_cards,
    )
    return BoardView(
        cards=_matching_cards(rows, query, context),
        health=ProjectionHealth.CURRENT if current else ProjectionHealth.STATE_UNKNOWN,
        source_watermark=view_source,
        projection_watermark=projection,
    )


def _expected_card_count(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str | None,
) -> int:
    row = connection.execute(
        """
        SELECT count(*) AS value
        FROM durability_acceptance_confirmations AS confirmation
        JOIN events AS event
          ON event.tenant_id = confirmation.tenant_id
         AND event.actor_principal_id = confirmation.principal_id
         AND event.client_command_id = confirmation.client_command_id
        JOIN tickets AS ticket
          ON ticket.tenant_id = event.tenant_id
         AND ticket.ticket_id = event.aggregate_id
        WHERE confirmation.tenant_id = %s AND event.kind = 'ticket.created'
          AND (%s::text IS NULL OR ticket.project_key = %s)
        """,
        (tenant_id, project_key, project_key),
    ).fetchone()
    return int(cast(int, row["value"])) if row else 0


def _query_filters(query: BoardQuery | None) -> tuple[str | None, str | None, str | None]:
    if query is None:
        return None, None, None
    return query.project_key, query.source_kind, query.source_ref


def _scoped_projection_position(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str | None,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT COALESCE(MAX(source_position), 0) AS value
        FROM board_projection_rows
        WHERE tenant_id = %s AND (%s::text IS NULL OR project_key = %s)
        """,
        (tenant_id, project_key, project_key),
    ).fetchone()


def _cursor_position(cursor: dict[str, object] | None) -> int:
    return int(cast(int, cursor["acceptance_position"])) if cursor else 0


def _scoped_watermarks(
    project_key: str | None,
    *,
    source: int,
    scoped_source: int,
    global_projection: int,
    scoped_projection: dict[str, object] | None,
) -> tuple[int, int]:
    if project_key is None:
        return source, global_projection
    projection = int(cast(int, scoped_projection["value"])) if scoped_projection else 0
    return scoped_source, projection


def _is_current(
    cursor: dict[str, object] | None,
    *,
    global_projection: int,
    source: int,
    projection: int,
    view_source: int,
    actual_cards: int,
    expected_cards: int,
) -> bool:
    return bool(
        cursor
        and cursor["health"] == "CURRENT"
        and cursor["blocked_outbox_id"] is None
        and global_projection == source
        and projection == view_source
        and actual_cards == expected_cards
    )


def _read_context_sets(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    rows: list[dict[str, object]],
) -> _ContextSets:
    ticket_ids = tuple(cast(UUID, row["ticket_id"]) for row in rows)
    return _ContextSets(
        tenant_display_identity=_context.tenant_display_identity(connection, tenant_id),
        change_references=_context.change_references_by_ticket(connection, tenant_id, ticket_ids),
        applied_labels=_context.applied_labels_by_ticket(connection, tenant_id, ticket_ids),
        human_waiting=_context.human_waiting_by_ticket(connection, tenant_id, ticket_ids),
        delivery_surface=_context.delivery_surface_by_ticket(connection, tenant_id, ticket_ids),
        inbox_threads=_context.inbox_threads_by_ticket(connection, tenant_id, ticket_ids),
    )


def _matching_cards(
    rows: list[dict[str, object]], query: BoardQuery | None, context: _ContextSets
) -> tuple[BoardCard, ...]:
    cards = tuple(_card(row, context) for row in rows)
    return tuple(card for card in cards if query is None or _matches(card, query))


def _project_source(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str | None,
) -> int:
    if project_key is None:
        return 0
    row = connection.execute(
        """
        SELECT COALESCE(MAX(confirmation.acceptance_position), 0) AS value
        FROM durability_acceptance_confirmations AS confirmation
        JOIN events AS event
          ON event.tenant_id = confirmation.tenant_id
         AND event.actor_principal_id = confirmation.principal_id
         AND event.client_command_id = confirmation.client_command_id
        JOIN event_links AS link
          ON link.tenant_id = event.tenant_id AND link.event_id = event.event_id
         AND link.subject_kind = 'ticket'
        JOIN tickets AS ticket
          ON ticket.tenant_id = link.tenant_id AND ticket.ticket_id = link.subject_id
        WHERE confirmation.tenant_id = %s AND ticket.project_key = %s
          AND event.kind = ANY(%s)
        """,
        (
            tenant_id,
            project_key,
            [kind.value for kind in _board_source_event_kinds()],
        ),
    ).fetchone()
    return int(cast(int, row["value"])) if row is not None else 0


def _board_source_event_kinds() -> tuple[EventKind, ...]:
    return tuple(_FOLD_DISPATCH)


def _create_card(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    payload: dict[str, object],
    position: int,
) -> None:
    project_key = _created_project(connection, tenant_id, message, payload)
    connection.execute(
        """
        INSERT INTO board_projection_rows (
            tenant_id, ticket_id, project_key, title, source_kind, source_ref,
            lane, underlying_lane, priority,
            stage_key, activity_class, custodian_id, assignee_id, blocker_reason,
            blocker_opened_at, risk, delivery_facts, ticket_version, source_position
        ) VALUES (%s, %s, %s, %s, %s, %s, 'backlog', NULL, %s,
            NULL, NULL, %s, NULL, NULL, NULL, NULL, '[]'::jsonb, 1, %s)
        ON CONFLICT (tenant_id, ticket_id) DO NOTHING
        """,
        (
            tenant_id,
            message["aggregate_id"],
            project_key,
            payload["title"],
            payload["source_kind"],
            payload["source_ref"],
            payload["priority"],
            UUID(str(payload["custodian_id"])),
            position,
        ),
    )


def _created_project(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    payload: dict[str, object],
) -> str:
    if "project_key" in payload:
        return str(payload["project_key"])
    row = connection.execute(
        "SELECT project_key FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
        (tenant_id, message["aggregate_id"]),
    ).fetchone()
    if row is None:
        raise ValueError("legacy ticket event has no authoritative project binding")
    return str(row["project_key"])


def _apply_custody_transfer(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    payload: dict[str, object],
    position: int,
) -> None:
    _update_card(
        connection,
        tenant_id,
        cast(UUID, message["aggregate_id"]),
        position,
        "custodian_id = %s, ticket_version = %s",
        (UUID(str(payload["to_custodian_id"])), int(cast(int, message["sequence"]))),
    )


def _apply_work(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    payload: dict[str, object],
    position: int,
) -> None:
    ticket_id = UUID(str(payload["ticket_id"]))
    operation = str(payload["operation"])
    data = cast(dict[str, object], payload["data"])
    version = int(cast(int, payload["work_version"]))
    if operation == "priority_changed":
        _update_card(
            connection,
            tenant_id,
            ticket_id,
            position,
            "priority = %s, ticket_version = %s",
            (data["to_priority"], version),
        )
        return
    if operation == "assignment_changed" and data["assignment_kind"] == "current_assignee":
        assignee = UUID(str(data["to_principal_id"])) if data["to_principal_id"] else None
        _update_card(
            connection,
            tenant_id,
            ticket_id,
            position,
            "assignee_id = %s, ticket_version = %s",
            (assignee, version),
        )
        return
    if operation in {"admitted", "deferred", "reopened"}:
        lane = "ready" if operation == "admitted" else "backlog"
        _set_lane(connection, tenant_id, ticket_id, position, lane, version)
        return
    if operation == "blocker_opened" and bool(data["board_impact"]):
        _open_blocker(connection, tenant_id, ticket_id, data, message, position, version)
        return
    if operation == "blocker_resolved":
        _resolve_blocker(connection, tenant_id, ticket_id, data, position, version)
        return
    _update_card(connection, tenant_id, ticket_id, position, "ticket_version = %s", (version,))


def _apply_workflow(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    payload: dict[str, object],
    position: int,
) -> None:
    ticket_id = UUID(str(payload["ticket_id"]))
    if cast(list[object], payload["lifecycle_facts"]):
        _update_card(
            connection,
            tenant_id,
            ticket_id,
            position,
            "lane = 'complete', underlying_lane = NULL",
            (),
        )
        return
    activity = cast(str | None, message["workflow_activity_class"])
    if activity is None and payload["operation"] in {"start", "transition"}:
        raise ValueError("schema-unknown: workflow activity fact")
    lane = "in_review" if activity == "verification" else "in_progress"
    connection.execute(
        """
        UPDATE board_projection_rows SET stage_key = %s,
            activity_class = COALESCE(%s, activity_class),
            underlying_lane = CASE WHEN lane = 'blocked' THEN %s ELSE underlying_lane END,
            lane = CASE WHEN lane = 'blocked' THEN lane ELSE %s END,
            source_position = %s
        WHERE tenant_id = %s AND ticket_id = %s
        """,
        (payload["stage"], activity, lane, lane, position, tenant_id, ticket_id),
    )


_FOLD_DISPATCH: Mapping[EventKind, _FoldHandler] = {
    EventKind.TICKET_CREATED: _create_card,
    EventKind.CUSTODY_TRANSFERRED: _apply_custody_transfer,
    EventKind.WORK_CHANGED: _apply_work,
    EventKind.WORKFLOW_CHANGED: _apply_workflow,
}


def _set_lane(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_id: UUID,
    position: int,
    lane: str,
    version: int,
) -> None:
    connection.execute(
        """
        UPDATE board_projection_rows SET
            underlying_lane = CASE WHEN lane = 'blocked' THEN %s ELSE NULL END,
            lane = CASE WHEN lane = 'blocked' THEN lane ELSE %s END,
            ticket_version = %s, source_position = %s
        WHERE tenant_id = %s AND ticket_id = %s
        """,
        (lane, lane, version, position, tenant_id, ticket_id),
    )


def _open_blocker(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_id: UUID,
    data: dict[str, object],
    message: dict[str, object],
    position: int,
    version: int,
) -> None:
    opened = cast(datetime, message["server_time"])
    connection.execute(
        """
        INSERT INTO board_projection_blockers (
            tenant_id, ticket_id, blocker_id, reason, opened_at
        ) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
        """,
        (tenant_id, ticket_id, UUID(str(data["blocker_id"])), data["reason"], opened),
    )
    connection.execute(
        """
        UPDATE board_projection_rows SET
            underlying_lane = CASE WHEN lane = 'blocked' THEN underlying_lane ELSE lane END,
            lane = 'blocked', blocker_reason = %s, blocker_opened_at = %s,
            ticket_version = %s, source_position = %s
        WHERE tenant_id = %s AND ticket_id = %s
        """,
        (data["reason"], opened, version, position, tenant_id, ticket_id),
    )


def _resolve_blocker(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_id: UUID,
    data: dict[str, object],
    position: int,
    version: int,
) -> None:
    connection.execute(
        """
        DELETE FROM board_projection_blockers
        WHERE tenant_id = %s AND ticket_id = %s AND blocker_id = %s
        """,
        (tenant_id, ticket_id, UUID(str(data["blocker_id"]))),
    )
    remaining = connection.execute(
        """
        SELECT reason, opened_at FROM board_projection_blockers
        WHERE tenant_id = %s AND ticket_id = %s ORDER BY opened_at, blocker_id LIMIT 1
        """,
        (tenant_id, ticket_id),
    ).fetchone()
    values: tuple[object, ...]
    if remaining is not None:
        detail = "blocker_reason = %s, blocker_opened_at = %s, ticket_version = %s"
        values = (remaining["reason"], remaining["opened_at"], version)
    else:
        detail = (
            "lane = COALESCE(underlying_lane, 'backlog'), underlying_lane = NULL, "
            "blocker_reason = NULL, blocker_opened_at = NULL, ticket_version = %s"
        )
        values = (version,)
    _update_card(connection, tenant_id, ticket_id, position, detail, values)


def _update_card(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    ticket_id: UUID,
    position: int,
    assignments: str,
    values: tuple[object, ...],
) -> None:
    query = sql.SQL(
        "UPDATE board_projection_rows SET {assignments}, source_position = %s "
        "WHERE tenant_id = %s AND ticket_id = %s"
    ).format(
        assignments=sql.SQL(assignments),
    )
    connection.execute(query, (*values, position, tenant_id, ticket_id))


def _card(row: dict[str, object], context: _ContextSets) -> BoardCard:
    delivery = cast(list[object], row["delivery_facts"])
    ticket_id = cast(UUID, row["ticket_id"])
    return BoardCard(
        ticket_id=ticket_id,
        project_key=str(row["project_key"]),
        title=str(row["title"]),
        lane=BoardLane(str(row["lane"])),
        underlying_lane=(
            BoardLane(str(row["underlying_lane"])) if row["underlying_lane"] else None
        ),
        priority=str(row["priority"]),
        stage_key=cast(str | None, row["stage_key"]),
        activity_class=cast(str | None, row["activity_class"]),
        custodian_id=cast(UUID, row["custodian_id"]),
        assignee_id=cast(UUID | None, row["assignee_id"]),
        blocker_reason=cast(str | None, row["blocker_reason"]),
        blocker_opened_at=cast(datetime | None, row["blocker_opened_at"]),
        risk=cast(str | None, row["risk"]),
        delivery_facts=tuple(str(item) for item in delivery),
        version=int(cast(int, row["ticket_version"])),
        tenant_display_identity=context.tenant_display_identity,
        change_references=context.change_references.get(ticket_id, ()),
        applied_labels=context.applied_labels.get(ticket_id, ()),
        human_waiting=context.human_waiting.get(ticket_id, _NOT_WAITING),
        delivery_surface_availability=context.delivery_surface.get(
            ticket_id, _NO_QUALIFYING_CHECKPOINT
        ),
        inbox_thread_ids=context.inbox_threads.get(ticket_id, ()),
    )


def _matches(card: BoardCard, query: BoardQuery) -> bool:
    return all(
        (
            query.lane is None or card.lane is query.lane,
            query.priority is None or card.priority == query.priority,
            query.stage_key is None or card.stage_key == query.stage_key,
            query.custodian_id is None or card.custodian_id == query.custodian_id,
            query.assignee_id is None or card.assignee_id == query.assignee_id,
            query.risk is None or card.risk == query.risk,
        )
    )
