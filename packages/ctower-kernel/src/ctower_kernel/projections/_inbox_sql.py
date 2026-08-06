"""Disposable native-inbox fold and recipient-scoped reads."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.projections.interface import (
    InboxMessage,
    InboxThread,
    InboxThreadList,
    InboxThreadSummary,
)
from ctower_kernel.record import Actor
from ctower_kernel.record.events import EventKind

__all__: tuple[str, ...] = ()


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
                    WHERE message.recipient_id = %s
                      AND message.position > COALESCE(read.through_position, 0)
                ) AS unread_count
            FROM inbox_projection_threads AS thread
            LEFT JOIN inbox_projection_messages AS message
              ON message.tenant_id = thread.tenant_id AND message.thread_id = thread.thread_id
            LEFT JOIN inbox_projection_reads AS read
              ON read.tenant_id = thread.tenant_id AND read.thread_id = thread.thread_id
             AND read.principal_id = %s
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


def read_thread(
    dsn: str,
    actor: Actor,
    thread_id: UUID,
    *,
    now: datetime,
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
        through = max(int(cast(int, row["position"])) for row in rows)
        connection.execute(
            """
            INSERT INTO inbox_projection_reads (
                tenant_id, thread_id, principal_id, through_position, read_at
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, thread_id, principal_id) DO UPDATE SET
                through_position = GREATEST(
                    inbox_projection_reads.through_position, EXCLUDED.through_position
                ),
                read_at = EXCLUDED.read_at
            """,
            (actor.tenant_id, thread_id, actor.principal_id, through, now),
        )
        return InboxThread(
            messages=tuple(_message(row) for row in rows),
            participants=(str(thread["participant_a_seat"]), str(thread["participant_b_seat"])),
            promoted_ticket_id=cast(UUID | None, thread["promoted_ticket_id"]),
            read_through_position=through,
            thread_id=thread_id,
        )


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
            recipient_id, recipient_seat, content, sent_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def _seat_key(connection: psycopg.Connection[dict[str, object]], actor: Actor) -> str:
    row = connection.execute(
        "SELECT seat_key FROM project_seats WHERE tenant_id = %s AND principal_id = %s",
        (actor.tenant_id, actor.principal_id),
    ).fetchone()
    return str(row["seat_key"]) if row is not None else "unaddressable"


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
    )
