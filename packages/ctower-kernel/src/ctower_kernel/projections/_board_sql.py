"""Disposable Board row fold and read mechanics."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from ctower_kernel.projections import BoardCard, BoardLane, BoardQuery, BoardView, ProjectionHealth
from ctower_kernel.record.events import EventKind

__all__: tuple[str, ...] = ()


def apply_message(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
) -> None:
    kind = EventKind(str(message["kind"]))
    payload = cast(dict[str, object], message["event_payload"])
    position = int(cast(int, message["acceptance_position"]))
    if kind is EventKind.TICKET_CREATED:
        _create_card(connection, tenant_id, message, payload, position)
    elif kind is EventKind.CUSTODY_TRANSFERRED:
        _update_card(
            connection,
            tenant_id,
            cast(UUID, message["aggregate_id"]),
            position,
            "custodian_id = %s, ticket_version = %s",
            (UUID(str(payload["to_custodian_id"])), int(cast(int, message["sequence"]))),
        )
    elif kind is EventKind.WORK_CHANGED:
        _apply_work(connection, tenant_id, message, payload, position)
    elif kind is EventKind.WORKFLOW_CHANGED:
        _apply_workflow(connection, tenant_id, message, payload, position)


def read_view(dsn: str, tenant_id: UUID, query: BoardQuery, *, source: int) -> BoardView:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        cursor = connection.execute(
            """
            SELECT acceptance_position, health, blocked_outbox_id
            FROM outbox_consumer_cursors
            WHERE consumer_key = 'board_projection' AND tenant_id = %s
              AND topic = 'record.events'
            """,
            (tenant_id,),
        ).fetchone()
        rows = connection.execute(
            "SELECT * FROM board_projection_rows WHERE tenant_id = %s ORDER BY ticket_id",
            (tenant_id,),
        ).fetchall()
        expected_row = connection.execute(
            """
            SELECT count(*) AS value
            FROM durability_acceptance_confirmations AS confirmation
            JOIN events AS event
              ON event.tenant_id = confirmation.tenant_id
             AND event.actor_principal_id = confirmation.principal_id
             AND event.client_command_id = confirmation.client_command_id
            WHERE confirmation.tenant_id = %s AND event.kind = 'ticket.created'
            """,
            (tenant_id,),
        ).fetchone()
    projection = int(cast(int, cursor["acceptance_position"])) if cursor else 0
    expected_cards = int(cast(int, expected_row["value"])) if expected_row else 0
    current = bool(
        cursor
        and cursor["health"] == "CURRENT"
        and cursor["blocked_outbox_id"] is None
        and projection == source
        and len(rows) == expected_cards
    )
    cards = tuple(_card(row) for row in rows)
    return BoardView(
        cards=tuple(card for card in cards if _matches(card, query)),
        health=ProjectionHealth.CURRENT if current else ProjectionHealth.STATE_UNKNOWN,
        source_watermark=source,
        projection_watermark=projection,
    )


def _create_card(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
    payload: dict[str, object],
    position: int,
) -> None:
    connection.execute(
        """
        INSERT INTO board_projection_rows (
            tenant_id, ticket_id, title, lane, underlying_lane, priority,
            stage_key, activity_class, custodian_id, assignee_id, blocker_reason,
            blocker_opened_at, risk, delivery_facts, ticket_version, source_position
        ) VALUES (%s, %s, %s, 'backlog', NULL, %s, NULL, NULL, %s, NULL, NULL,
            NULL, NULL, '[]'::jsonb, 1, %s)
        ON CONFLICT (tenant_id, ticket_id) DO NOTHING
        """,
        (
            tenant_id,
            message["aggregate_id"],
            payload["title"],
            payload["priority"],
            UUID(str(payload["custodian_id"])),
            position,
        ),
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


def _card(row: dict[str, object]) -> BoardCard:
    delivery = cast(list[object], row["delivery_facts"])
    return BoardCard(
        ticket_id=cast(UUID, row["ticket_id"]),
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
