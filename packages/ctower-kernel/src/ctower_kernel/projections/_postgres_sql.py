"""Disposable Board projection fold, cursor validation, and tenant-safe reads."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_kernel.projections import (
    BoardCard,
    BoardFacts,
    BoardLane,
    BoardQuery,
    BoardView,
    ProjectionHealth,
    derive_board_card,
)
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()

_KNOWN_EVENTS = frozenset(
    {
        "bootstrap.first_tenant_created",
        "ticket.created",
        "ticket.custody_transferred",
        "proof.changed",
        "workflow.changed",
        "work.changed",
    }
)


def catch_up(dsn: str, tenant_id: UUID, through_watermark: int | None) -> BoardView:
    """Fold only after proving the global source prefix is contiguous and understood."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        source = _source_watermark(connection)
        target = source if through_watermark is None else through_watermark
        cursor = _cursor(connection, tenant_id)
        if target < cursor or target < 0:
            _unknown(connection, tenant_id, cursor, "requested-watermark-behind")
            return _view(connection, tenant_id, BoardQuery())
        if target > source:
            _unknown(connection, tenant_id, cursor, "requested-watermark-ahead")
            return _view(connection, tenant_id, BoardQuery())
        if target < source:
            _unknown(connection, tenant_id, cursor, "requested-watermark-behind-source")
            return _view(connection, tenant_id, BoardQuery())
        if cursor > source:
            _unknown(connection, tenant_id, cursor, "projection-ahead")
            return _view(connection, tenant_id, BoardQuery())
        fault = _prefix_fault(connection, cursor, target)
        if fault is not None:
            _unknown(connection, tenant_id, cursor, fault)
            return _view(connection, tenant_id, BoardQuery())
        cards = tuple(
            derive_board_card(facts) for facts in _authoritative_facts(connection, tenant_id)
        )
        _replace_rows(connection, tenant_id, cards, target)
        _current(connection, tenant_id, target)
        return _view(connection, tenant_id, BoardQuery())


def board(dsn: str, actor: Actor, query: BoardQuery) -> BoardView:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        return _view(connection, actor.tenant_id, query)


def rebuild(dsn: str, tenant_id: UUID) -> BoardView:
    """Discard only disposable rows/cursor and replay the same source prefix from zero."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        connection.execute("DELETE FROM board_projection_rows WHERE tenant_id = %s", (tenant_id,))
        connection.execute("DELETE FROM projection_cursors WHERE tenant_id = %s", (tenant_id,))
    return catch_up(dsn, tenant_id, None)


def _source_watermark(connection: psycopg.Connection[dict[str, object]]) -> int:
    row = cast(
        dict[str, object],
        connection.execute(
            "SELECT COALESCE(max(record_position), 0) AS value FROM events"
        ).fetchone(),
    )
    return int(cast(int, row["value"]))


def _cursor(connection: psycopg.Connection[dict[str, object]], tenant_id: UUID) -> int:
    row = connection.execute(
        "SELECT projection_watermark FROM projection_cursors WHERE tenant_id = %s FOR UPDATE",
        (tenant_id,),
    ).fetchone()
    return int(cast(int, row["projection_watermark"])) if row else 0


def _prefix_fault(
    connection: psycopg.Connection[dict[str, object]], cursor: int, target: int
) -> str | None:
    del cursor
    if target <= 0:
        return None
    gap = connection.execute(
        """
        SELECT position FROM generate_series(%s::bigint, %s::bigint) AS position
        LEFT JOIN events ON events.record_position = position
        WHERE events.event_id IS NULL LIMIT 1
        """,
        (1, target),
    ).fetchone()
    if gap is not None:
        return f"record-position-gap:{gap['position']}"
    unknown = connection.execute(
        """
        SELECT record_position, kind FROM events
        WHERE record_position <= %s
          AND NOT (kind = ANY(%s))
        ORDER BY record_position LIMIT 1
        """,
        (target, sorted(_KNOWN_EVENTS)),
    ).fetchone()
    if unknown is not None:
        return f"unknown-event:{unknown['record_position']}:{unknown['kind']}"
    return None


def _authoritative_facts(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID
) -> tuple[BoardFacts, ...]:
    rows = connection.execute(
        """
        SELECT t.ticket_id, t.title, t.priority, t.custodian_principal_id, t.version,
            episode.state AS lifecycle_state,
            COALESCE(admission.admitted, false) AS admitted,
            run.current_stage, run.activity_class,
            COALESCE(run.version > 1, false) AS workflow_active,
            assignee.principal_id AS assignee_id,
            blocker.reason AS blocker_reason, blocker.opened_at AS blocker_opened_at
        FROM tickets AS t
        JOIN lifecycle_episodes AS episode
          ON episode.tenant_id = t.tenant_id AND episode.ticket_id = t.ticket_id
         AND episode.episode_number = t.current_episode
        LEFT JOIN LATERAL (
            SELECT admitted FROM admission_facts
            WHERE tenant_id = t.tenant_id AND ticket_id = t.ticket_id
              AND episode_number = t.current_episode
            ORDER BY fact_sequence DESC LIMIT 1
        ) AS admission ON true
        LEFT JOIN workflow_runs AS run
          ON run.tenant_id = t.tenant_id AND run.ticket_id = t.ticket_id
         AND run.episode_number = t.current_episode
        LEFT JOIN LATERAL (
            SELECT principal_id FROM assignment_intervals
            WHERE tenant_id = t.tenant_id AND ticket_id = t.ticket_id
              AND assignment_kind = 'current_assignee' AND released_at IS NULL
            ORDER BY interval_sequence DESC LIMIT 1
        ) AS assignee ON true
        LEFT JOIN LATERAL (
            SELECT reason, opened_at FROM blocker_heads
            WHERE tenant_id = t.tenant_id AND ticket_id = t.ticket_id
              AND board_impact AND resolved_at IS NULL
            ORDER BY opened_at, blocker_id LIMIT 1
        ) AS blocker ON true
        WHERE t.tenant_id = %s AND episode.state <> 'cancelled'
        ORDER BY t.ticket_id
        """,
        (tenant_id,),
    ).fetchall()
    return tuple(_facts(row) for row in rows)


def _facts(row: dict[str, object]) -> BoardFacts:
    return BoardFacts(
        ticket_id=cast(UUID, row["ticket_id"]),
        title=str(row["title"]),
        priority=str(row["priority"]),
        lifecycle_state=str(row["lifecycle_state"]),
        admitted=bool(row["admitted"]),
        workflow_active=bool(row["workflow_active"]),
        stage_key=cast(str | None, row["current_stage"]),
        activity_class=cast(str | None, row["activity_class"]),
        custodian_id=cast(UUID, row["custodian_principal_id"]),
        assignee_id=cast(UUID | None, row["assignee_id"]),
        blocker_reason=cast(str | None, row["blocker_reason"]),
        blocker_opened_at=cast(datetime | None, row["blocker_opened_at"]),
        risk=None,
        delivery_facts=(),
        version=int(cast(int, row["version"])),
    )


def _replace_rows(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    cards: tuple[BoardCard, ...],
    source: int,
) -> None:
    connection.execute("DELETE FROM board_projection_rows WHERE tenant_id = %s", (tenant_id,))
    connection.cursor().executemany(
        """
        INSERT INTO board_projection_rows (
            tenant_id, ticket_id, title, lane, underlying_lane, priority, stage_key,
            activity_class, custodian_id, assignee_id, blocker_reason, blocker_opened_at,
            risk, delivery_facts, ticket_version, source_position
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            (
                tenant_id,
                card.ticket_id,
                card.title,
                card.lane.value,
                card.underlying_lane.value if card.underlying_lane else None,
                card.priority,
                card.stage_key,
                card.activity_class,
                card.custodian_id,
                card.assignee_id,
                card.blocker_reason,
                card.blocker_opened_at,
                card.risk,
                Jsonb(list(card.delivery_facts)),
                card.version,
                source,
            )
            for card in cards
        ),
    )


def _current(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, watermark: int
) -> None:
    connection.execute(
        """
        INSERT INTO projection_cursors (
            tenant_id, projection_watermark, health, detail, updated_at
        ) VALUES (%s, %s, 'CURRENT', 'current', CURRENT_TIMESTAMP)
        ON CONFLICT (tenant_id) DO UPDATE SET
            projection_watermark = EXCLUDED.projection_watermark,
            health = 'CURRENT', detail = 'current', updated_at = CURRENT_TIMESTAMP
        """,
        (tenant_id, watermark),
    )


def _unknown(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, cursor: int, detail: str
) -> None:
    connection.execute(
        """
        INSERT INTO projection_cursors (
            tenant_id, projection_watermark, health, detail, updated_at
        ) VALUES (%s, %s, 'STATE_UNKNOWN', %s, CURRENT_TIMESTAMP)
        ON CONFLICT (tenant_id) DO UPDATE SET
            health = 'STATE_UNKNOWN', detail = EXCLUDED.detail,
            updated_at = CURRENT_TIMESTAMP
        """,
        (tenant_id, cursor, detail),
    )


def _view(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, query: BoardQuery
) -> BoardView:
    source = _source_watermark(connection)
    cursor_row = connection.execute(
        "SELECT projection_watermark, health FROM projection_cursors WHERE tenant_id = %s",
        (tenant_id,),
    ).fetchone()
    projection = int(cast(int, cursor_row["projection_watermark"])) if cursor_row else 0
    stored_health = str(cursor_row["health"]) if cursor_row else "STATE_UNKNOWN"
    rows = connection.execute(
        "SELECT * FROM board_projection_rows WHERE tenant_id = %s ORDER BY ticket_id",
        (tenant_id,),
    ).fetchall()
    cards = tuple(_card(row) for row in rows)
    expected = cast(
        dict[str, object],
        connection.execute(
            """
        SELECT count(*) AS value FROM tickets AS t
        JOIN lifecycle_episodes AS episode
          ON episode.tenant_id = t.tenant_id AND episode.ticket_id = t.ticket_id
         AND episode.episode_number = t.current_episode
        WHERE t.tenant_id = %s AND episode.state <> 'cancelled'
        """,
            (tenant_id,),
        ).fetchone(),
    )
    missing = int(cast(int, expected["value"])) != len(cards)
    source_fault = _prefix_fault(connection, 0, source)
    current = (
        stored_health == "CURRENT" and projection == source and not missing and source_fault is None
    )
    return BoardView(
        cards=tuple(card for card in cards if _matches(card, query)),
        health=ProjectionHealth.CURRENT if current else ProjectionHealth.STATE_UNKNOWN,
        source_watermark=source,
        projection_watermark=projection,
    )


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
