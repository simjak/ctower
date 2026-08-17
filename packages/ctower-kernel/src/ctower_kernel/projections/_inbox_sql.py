"""Disposable native-inbox fold and recipient-scoped reads."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.projections.inbox import (
    InboxDeliveryState,
    InboxMessageReadState,
    InboxReadState,
)
from ctower_kernel.projections.interface import (
    InboxCorrespondent,
    InboxCorrespondentList,
    InboxMessage,
    InboxThread,
    InboxThreadList,
    InboxThreadSummary,
)
from ctower_kernel.record import Actor
from ctower_kernel.record.events import EventKind
from ctower_kernel.record.inbox_events import InboxSeverity

__all__: tuple[str, ...] = ()

#: What the projection names a principal that holds no seat row: it can neither
#: receive a message nor address one, so it is an identity without an address.
_UNADDRESSABLE = "unaddressable"


def apply_message(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    message: dict[str, object],
) -> None:
    kind = EventKind(str(message["kind"]))
    payload = cast(dict[str, object], message["event_payload"])
    if kind is EventKind.INBOX_THREAD_OPENED:
        _open_thread(connection, tenant_id, payload)
    elif kind is EventKind.INBOX_MESSAGE_APPENDED:
        _append_message(connection, tenant_id, payload, cast(datetime, message["server_time"]))
    elif kind in {EventKind.INBOX_MESSAGE_DELIVERED, EventKind.INBOX_MESSAGE_READ}:
        _apply_delivery(
            connection,
            tenant_id,
            kind,
            payload,
            cast(UUID, message["event_id"]),
            cast(datetime, message["server_time"]),
        )
    elif kind is EventKind.INBOX_THREAD_PROMOTED_TO_TICKET:
        connection.execute(
            """
            UPDATE inbox_projection_threads SET promoted_ticket_id = %s
            WHERE tenant_id = %s AND thread_id = %s
            """,
            (UUID(str(payload["ticket_id"])), tenant_id, UUID(str(payload["thread_id"]))),
        )


def list_threads(dsn: str, actor: Actor, *, unread: bool) -> InboxThreadList:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        seat_key = _seat_key(connection, actor)
        rows = connection.execute(
            """
            SELECT thread.thread_id, thread.promoted_ticket_id,
                thread.last_message_at, thread.last_message_preview,
                CASE WHEN thread.participant_a_id = %s
                     THEN thread.participant_b_seat
                     ELSE thread.participant_a_seat END AS other_agent,
                count(message.message_id) FILTER (
                    WHERE message.recipient_id = %s AND message.read_at IS NULL
                ) AS unread_count
            FROM inbox_projection_threads AS thread
            LEFT JOIN inbox_projection_messages AS message
              ON message.tenant_id = thread.tenant_id AND message.thread_id = thread.thread_id
            WHERE thread.tenant_id = %s
              AND %s IN (thread.participant_a_id, thread.participant_b_id)
            GROUP BY thread.thread_id, thread.promoted_ticket_id,
                thread.last_message_at, thread.last_message_preview,
                thread.participant_a_id, thread.participant_a_seat, thread.participant_b_seat
            ORDER BY thread.last_message_at DESC, thread.thread_id
            """,
            (
                actor.principal_id,
                actor.principal_id,
                actor.tenant_id,
                actor.principal_id,
            ),
        ).fetchall()
    summaries = tuple(_summary(row) for row in rows if not unread or int(row["unread_count"]) > 0)
    return InboxThreadList(
        recipient=seat_key,
        threads=summaries,
        total_unread=sum(item.unread_count for item in summaries),
        unread_only=unread,
    )


def list_correspondents(
    dsn: str, actor: Actor, project_key: str | None = None
) -> InboxCorrespondentList:
    """Read the addresses this principal can open a thread to, and only those.

    The seats are the persisted ones, not a catalog of names a fleet might use,
    and they are narrowed to exactly what the send command accepts as an
    address. That command resolves a recipient by ``(tenant_id, seat_key)``
    while the registry only makes a seat key unique per project, so three legal
    registry states have no address in them at all: a key two seats share, which
    refuses as ambiguous; the reader's own seat, which refuses as self; and a
    reader holding no seat, which cannot address anybody. Each is absent here,
    because an address the command will not accept is not an address, and a
    picker that offered one would be inviting a refusal.
    """

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        seat_key = _seat_key(connection, actor)
        rows: list[dict[str, object]] = []
        if seat_key != _UNADDRESSABLE:
            rows = connection.execute(
                """
                SELECT project_key, seat_key FROM project_seats AS seat
                WHERE tenant_id = %s AND principal_id <> %s
                  AND (%s::text IS NULL OR project_key = %s)
                  AND NOT EXISTS (
                      SELECT 1 FROM project_seats AS sharing
                      WHERE sharing.tenant_id = seat.tenant_id
                        AND sharing.project_key = seat.project_key
                        AND sharing.seat_key = seat.seat_key
                        AND sharing.principal_id <> seat.principal_id
                  )
                ORDER BY seat_key
                """,
                (actor.tenant_id, actor.principal_id, project_key, project_key),
            ).fetchall()
    return InboxCorrespondentList(
        correspondents=tuple(
            InboxCorrespondent(project_key=str(row["project_key"]), seat_key=str(row["seat_key"]))
            for row in rows
        ),
        sender=seat_key,
    )


def read_thread(
    dsn: str,
    actor: Actor,
    thread_id: UUID,
) -> InboxThread | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        thread = connection.execute(
            """
            SELECT * FROM inbox_projection_threads
            WHERE tenant_id = %s AND thread_id = %s
              AND %s IN (participant_a_id, participant_b_id)
            """,
            (actor.tenant_id, thread_id, actor.principal_id),
        ).fetchone()
        if thread is None:
            return None
        rows = connection.execute(
            """
            SELECT * FROM inbox_projection_messages
            WHERE tenant_id = %s AND thread_id = %s ORDER BY position
            """,
            (actor.tenant_id, thread_id),
        ).fetchall()
        if not rows:
            raise RuntimeError("projected inbox thread has no message")
        incoming_unread = [
            int(cast(int, row["position"]))
            for row in rows
            if row["recipient_id"] == actor.principal_id and row["read_at"] is None
        ]
        through = (
            min(incoming_unread) - 1
            if incoming_unread
            else max(int(cast(int, row["position"])) for row in rows)
        )
        return InboxThread(
            messages=tuple(_message(row) for row in rows),
            participants=(str(thread["participant_a_seat"]), str(thread["participant_b_seat"])),
            promoted_ticket_id=cast(UUID | None, thread["promoted_ticket_id"]),
            read_through_position=through,
            thread_id=thread_id,
        )


def read_state(dsn: str, actor: Actor, thread_id: UUID) -> InboxReadState | None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_projection")
        thread = connection.execute(
            """
            SELECT 1 FROM inbox_projection_threads
            WHERE tenant_id = %s AND thread_id = %s
              AND %s IN (participant_a_id, participant_b_id)
            """,
            (actor.tenant_id, thread_id, actor.principal_id),
        ).fetchone()
        if thread is None:
            return None
        rows = connection.execute(
            """
            SELECT * FROM inbox_projection_messages
            WHERE tenant_id = %s AND thread_id = %s ORDER BY position
            """,
            (actor.tenant_id, thread_id),
        ).fetchall()
    return InboxReadState(tuple(_read_state(row) for row in rows), thread_id)


def _open_thread(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    payload: dict[str, object],
) -> None:
    opener = cast(dict[str, object], payload["opener"])
    recipient = cast(dict[str, object], payload["recipient"])
    connection.execute(
        """
        INSERT INTO inbox_projection_threads (
            tenant_id, thread_id, participant_a_id, participant_a_seat,
            participant_b_id, participant_b_seat
        ) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
        """,
        (
            tenant_id,
            UUID(str(payload["thread_id"])),
            UUID(str(opener["principal_id"])),
            opener["seat_key"],
            UUID(str(recipient["principal_id"])),
            recipient["seat_key"],
        ),
    )


def _append_message(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    payload: dict[str, object],
    sent_at: datetime,
) -> None:
    sender = cast(dict[str, object], payload["sender"])
    recipient = cast(dict[str, object], payload["recipient"])
    thread_id = UUID(str(payload["thread_id"]))
    connection.execute(
        """
        INSERT INTO inbox_projection_messages (
            tenant_id, thread_id, message_id, position, sender_id, sender_seat,
            recipient_id, recipient_seat, content, sent_at, severity
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            tenant_id,
            thread_id,
            UUID(str(payload["message_id"])),
            payload["position"],
            UUID(str(sender["principal_id"])),
            sender["seat_key"],
            UUID(str(recipient["principal_id"])),
            recipient["seat_key"],
            payload["text"],
            sent_at,
            payload.get("severity", "info"),
        ),
    )
    connection.execute(
        """
        UPDATE inbox_projection_threads SET
            last_message_at = %s, last_message_preview = left(%s, 500)
        WHERE tenant_id = %s AND thread_id = %s
        """,
        (sent_at, payload["text"], tenant_id, thread_id),
    )


def _apply_delivery(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    kind: EventKind,
    payload: dict[str, object],
    event_id: UUID,
    recorded_at: datetime,
) -> None:
    is_read = kind is EventKind.INBOX_MESSAGE_READ
    if is_read:
        existing = connection.execute(
            """
            SELECT delivered_event_id FROM inbox_projection_messages
            WHERE tenant_id = %s AND message_id = %s
            """,
            (tenant_id, UUID(str(payload["message_id"]))),
        ).fetchone()
        if existing is None or existing["delivered_event_id"] is None:
            raise ValueError("inbox read fact requires a projected delivery fact")
    values = (
        event_id,
        recorded_at,
        tenant_id,
        UUID(str(payload["thread_id"])),
        UUID(str(payload["message_id"])),
        UUID(str(cast(dict[str, object], payload["recipient"])["principal_id"])),
    )
    if is_read:
        connection.execute(
            """
            UPDATE inbox_projection_messages
            SET read_event_id = COALESCE(read_event_id, %s),
                read_at = COALESCE(read_at, %s)
            WHERE tenant_id = %s AND thread_id = %s AND message_id = %s
              AND recipient_id = %s
            """,
            values,
        )
    else:
        connection.execute(
            """
            UPDATE inbox_projection_messages
            SET delivered_event_id = COALESCE(delivered_event_id, %s),
                delivered_at = COALESCE(delivered_at, %s)
            WHERE tenant_id = %s AND thread_id = %s AND message_id = %s
              AND recipient_id = %s
            """,
            values,
        )


def _seat_key(connection: psycopg.Connection[dict[str, object]], actor: Actor) -> str:
    row = connection.execute(
        "SELECT seat_key FROM project_seats WHERE tenant_id = %s AND principal_id = %s",
        (actor.tenant_id, actor.principal_id),
    ).fetchone()
    return str(row["seat_key"]) if row is not None else _UNADDRESSABLE


def _summary(row: dict[str, object]) -> InboxThreadSummary:
    return InboxThreadSummary(
        last_message_at=cast(datetime, row["last_message_at"]),
        last_message_preview=str(row["last_message_preview"]),
        other_agent=str(row["other_agent"]),
        promoted_ticket_id=cast(UUID | None, row["promoted_ticket_id"]),
        thread_id=cast(UUID, row["thread_id"]),
        unread_count=int(cast(int, row["unread_count"])),
    )


def _message(row: dict[str, object]) -> InboxMessage:
    return InboxMessage(
        from_seat=str(row["sender_seat"]),
        message_id=cast(UUID, row["message_id"]),
        position=int(cast(int, row["position"])),
        sent_at=cast(datetime, row["sent_at"]),
        text=str(row["content"]),
        to=str(row["recipient_seat"]),
        severity=InboxSeverity(str(row.get("severity", "info"))),
    )


def _read_state(row: dict[str, object]) -> InboxMessageReadState:
    state = (
        InboxDeliveryState.READ
        if row["read_event_id"] is not None
        else InboxDeliveryState.DELIVERED
        if row["delivered_event_id"] is not None
        else InboxDeliveryState.SENT
    )
    return InboxMessageReadState(
        delivered_at=cast(datetime | None, row["delivered_at"]),
        delivered_event_id=cast(UUID | None, row["delivered_event_id"]),
        message_id=cast(UUID, row["message_id"]),
        position=int(cast(int, row["position"])),
        read_at=cast(datetime | None, row["read_at"]),
        read_event_id=cast(UUID | None, row["read_event_id"]),
        recipient=str(row["recipient_seat"]),
        state=state,
        severity=InboxSeverity(str(row.get("severity", "info"))),
    )
