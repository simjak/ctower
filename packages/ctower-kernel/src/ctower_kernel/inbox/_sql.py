"""Record-owned SQL for native inbox commands."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.inbox._events import _message_event, _opened_event, _promotion_event
from ctower_kernel.inbox.models import (
    InboxPromotionCommand,
    InboxPromotionResult,
    InboxSendCommand,
    InboxSendResult,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import event_digest
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.inbox_events import InboxParticipant
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    project_mutation_refusal,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_MAX_MESSAGE_LENGTH = 65536


def send_message(
    dsn: str,
    actor: Actor,
    command: InboxSendCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxSendResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _send_result(replay)
        validation = _validate_send(connection, actor, command)
        if isinstance(validation, RecordProblem):
            return _refuse(
                transaction, actor, command.client_command_id, request_digest, validation, now
            )
        sender, recipient, thread = validation
        thread_id = command.thread_id or uuid7(now)
        durable = transaction.require_durable_subjects(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (("inbox_thread", thread_id),),
            now=now,
        )
        if durable is not None:
            return durable
        result, commits, final_hash = _message_commits(
            actor,
            command,
            sender,
            recipient,
            thread,
            thread_id=thread_id,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
        transaction.commit_batch(
            commits,
            response_body=result.response_payload(),
            status_code=201,
            telemetry=telemetry,
            now=now,
            subjects=(("inbox_thread", thread_id),),
        )
        _persist_message(
            connection,
            actor,
            result,
            sender,
            recipient,
            command.text,
            final_hash,
            is_new=thread is None,
        )
        return result


def promote_thread(
    dsn: str,
    actor: Actor,
    command: InboxPromotionCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxPromotionResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _promotion_result(replay)
        thread = _lock_thread(connection, actor.tenant_id, command.thread_id)
        problem = _promotion_problem(connection, actor, command, thread)
        if problem is not None:
            return _refuse(
                transaction, actor, command.client_command_id, request_digest, problem, now
            )
        durable = transaction.require_durable_subjects(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (("inbox_thread", command.thread_id), ("ticket", command.ticket_id)),
            now=now,
        )
        if durable is not None:
            return durable
        locked = cast(dict[str, object], thread)
        return _commit_promotion(
            connection,
            transaction,
            actor,
            command,
            last_hash=bytes(cast(bytes, locked["last_event_hash"])),
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _commit_promotion(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: InboxPromotionCommand,
    *,
    last_hash: bytes,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxPromotionResult:
    event, outbox_id = _promotion_event(actor, command, last_hash, request_digest, now, telemetry)
    result = InboxPromotionResult(
        command.client_command_id,
        event.event_id,
        command.thread_id,
        event.sequence,
        command.ticket_id,
    )
    subjects = (("inbox_thread", command.thread_id), ("ticket", command.ticket_id))
    transaction.commit_batch(
        (EventCommit(event, outbox_id),),
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry,
        now=now,
        subjects=subjects,
    )
    connection.execute(
        """
        UPDATE inbox_threads SET version = %s, last_event_hash = %s
        WHERE tenant_id = %s AND thread_id = %s AND version = %s
        """,
        (
            result.thread_version,
            event_digest(event),
            actor.tenant_id,
            command.thread_id,
            command.expected_thread_version,
        ),
    )
    connection.execute(
        """
        INSERT INTO inbox_ticket_links (
            thread_id, tenant_id, ticket_id, event_id, promoted_by, promoted_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            command.thread_id,
            actor.tenant_id,
            command.ticket_id,
            event.event_id,
            actor.principal_id,
            now,
        ),
    )
    return result


def _validate_send(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxSendCommand,
) -> tuple[InboxParticipant, InboxParticipant, dict[str, object] | None] | RecordProblem:
    if not isinstance(command.text, str) or not 1 <= len(command.text) <= _MAX_MESSAGE_LENGTH:
        return _problem(
            command.client_command_id, "invalid-request", 422, "Message text is invalid"
        )
    sender = _actor_seat(connection, actor)
    if sender is None:
        return _problem(
            command.client_command_id,
            "inbox-sender-unaddressable",
            422,
            "The authenticated principal has no addressable project seat.",
        )
    if command.thread_id is None:
        return _new_participants(connection, actor, command, sender)
    return _existing_participants(connection, actor, command, sender)


def _existing_participants(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxSendCommand,
    sender: InboxParticipant,
) -> tuple[InboxParticipant, InboxParticipant, dict[str, object]] | RecordProblem:
    if command.thread_id is None:
        raise RuntimeError("existing-thread validation requires a thread identity")
    thread = _lock_thread(connection, actor.tenant_id, command.thread_id)
    if thread is None:
        return _unavailable(command.client_command_id)
    participants = _thread_participants(thread)
    if sender.principal_id not in {item.principal_id for item in participants}:
        return _unavailable(command.client_command_id)
    recipient = (
        participants[1] if participants[0].principal_id == sender.principal_id else participants[0]
    )
    if command.to != recipient.seat_key:
        return _problem(
            command.client_command_id,
            "inbox-thread-participant-mismatch",
            409,
            "The requested recipient is not the other participant in this thread.",
        )
    position = connection.execute(
        """
        SELECT COALESCE(max(position) + 1, 1) AS next_position
        FROM inbox_messages
        WHERE tenant_id = %s AND thread_id = %s
        """,
        (actor.tenant_id, command.thread_id),
    ).fetchone()
    if position is None:
        raise RuntimeError("inbox message position query returned no row")
    thread["next_position"] = position["next_position"]
    return sender, recipient, thread


def _new_participants(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxSendCommand,
    sender: InboxParticipant,
) -> tuple[InboxParticipant, InboxParticipant, None] | RecordProblem:
    rows = connection.execute(
        """
        SELECT principal_id, seat_key FROM project_seats
        WHERE tenant_id = %s AND seat_key = %s ORDER BY principal_id
        """,
        (actor.tenant_id, command.to),
    ).fetchall()
    if not rows:
        return _problem(
            command.client_command_id,
            "inbox-recipient-not-found",
            404,
            "No project seat has the requested inbox address.",
        )
    if len(rows) > 1:
        return _problem(
            command.client_command_id,
            "inbox-recipient-ambiguous",
            409,
            "The requested inbox address is not unique within this tenant.",
        )
    recipient = InboxParticipant(cast(UUID, rows[0]["principal_id"]), str(rows[0]["seat_key"]))
    if recipient.principal_id == actor.principal_id:
        return _problem(
            command.client_command_id,
            "inbox-recipient-self",
            422,
            "A native inbox message requires another agent as recipient.",
        )
    return sender, recipient, None


def _actor_seat(
    connection: psycopg.Connection[dict[str, object]], actor: Actor
) -> InboxParticipant | None:
    row = connection.execute(
        """
        SELECT principal_id, seat_key FROM project_seats
        WHERE tenant_id = %s AND principal_id = %s
        """,
        (actor.tenant_id, actor.principal_id),
    ).fetchone()
    if row is None:
        return None
    return InboxParticipant(cast(UUID, row["principal_id"]), str(row["seat_key"]))


def _lock_thread(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, thread_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT * FROM inbox_threads
        WHERE tenant_id = %s AND thread_id = %s
        FOR UPDATE
        """,
        (tenant_id, thread_id),
    ).fetchone()


def _thread_participants(thread: dict[str, object]) -> tuple[InboxParticipant, InboxParticipant]:
    return (
        InboxParticipant(cast(UUID, thread["participant_a_id"]), str(thread["participant_a_seat"])),
        InboxParticipant(cast(UUID, thread["participant_b_id"]), str(thread["participant_b_seat"])),
    )


def _message_commits(
    actor: Actor,
    command: InboxSendCommand,
    sender: InboxParticipant,
    recipient: InboxParticipant,
    thread: dict[str, object] | None,
    *,
    thread_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[InboxSendResult, tuple[EventCommit, ...], bytes]:
    message_id = uuid7(now)
    commits: list[EventCommit] = []
    if thread is None:
        opened = _opened_event(
            actor,
            command,
            sender,
            recipient,
            thread_id,
            request_digest,
            now,
            telemetry,
        )
        commits.append(EventCommit(opened, uuid7(now)))
        previous_hash, sequence, position = event_digest(opened), 2, 1
    else:
        previous_hash = bytes(cast(bytes, thread["last_event_hash"]))
        sequence = int(cast(int, thread["version"])) + 1
        position = int(
            cast(
                int,
                thread.get("next_position", 0),
            )
        )
    message = _message_event(
        actor,
        command,
        sender,
        recipient,
        thread_id=thread_id,
        message_id=message_id,
        position=position,
        previous_hash=previous_hash,
        sequence=sequence,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    commits.append(EventCommit(message, uuid7(now)))
    result = InboxSendResult(
        command.client_command_id,
        tuple(item.event.event_id for item in commits),
        sender.seat_key,
        message_id,
        position,
        now,
        thread_id,
        sequence,
        recipient.seat_key,
    )
    return result, tuple(commits), event_digest(message)


def _persist_message(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    result: InboxSendResult,
    sender: InboxParticipant,
    recipient: InboxParticipant,
    text: str,
    final_hash: bytes,
    *,
    is_new: bool,
) -> None:
    if is_new:
        connection.execute(
            """
            INSERT INTO inbox_threads (
                thread_id, tenant_id, participant_a_id, participant_a_seat,
                participant_b_id, participant_b_seat, version, last_event_hash,
                opened_by, opened_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                result.thread_id,
                actor.tenant_id,
                sender.principal_id,
                sender.seat_key,
                recipient.principal_id,
                recipient.seat_key,
                result.thread_version,
                final_hash,
                actor.principal_id,
                result.sent_at,
            ),
        )
    else:
        connection.execute(
            """
            UPDATE inbox_threads SET version = %s, last_event_hash = %s
            WHERE tenant_id = %s AND thread_id = %s
            """,
            (result.thread_version, final_hash, actor.tenant_id, result.thread_id),
        )
    connection.execute(
        """
        INSERT INTO inbox_messages (
            message_id, tenant_id, thread_id, position, sender_id, sender_seat,
            recipient_id, recipient_seat, content, event_id, sent_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.message_id,
            actor.tenant_id,
            result.thread_id,
            result.position,
            sender.principal_id,
            sender.seat_key,
            recipient.principal_id,
            recipient.seat_key,
            text,
            result.message_id,
            result.sent_at,
        ),
    )


def _promotion_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxPromotionCommand,
    thread: dict[str, object] | None,
) -> RecordProblem | None:
    if thread is None or actor.principal_id not in {
        thread.get("participant_a_id"),
        thread.get("participant_b_id"),
    }:
        return _unavailable(command.client_command_id)
    current = int(cast(int, thread["version"]))
    if current != command.expected_thread_version:
        return RecordProblem(
            "version-conflict",
            "The inbox thread version does not match the expected version.",
            409,
            "Inbox thread version conflict",
            command.client_command_id,
            current,
        )
    if (
        connection.execute(
            "SELECT 1 FROM inbox_ticket_links WHERE tenant_id = %s AND thread_id = %s",
            (actor.tenant_id, command.thread_id),
        ).fetchone()
        is not None
    ):
        return _problem(
            command.client_command_id,
            "inbox-already-promoted",
            409,
            "The inbox thread is already linked to a ticket.",
        )
    scope = project_mutation_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        command_id=command.client_command_id,
        ticket_ids=(command.ticket_id,),
    )
    if scope is not None:
        return scope
    if (
        connection.execute(
            "SELECT 1 FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
            (actor.tenant_id, command.ticket_id),
        ).fetchone()
        is None
    ):
        return _unavailable(command.client_command_id)
    return None


def _send_result(payload: dict[str, object]) -> InboxSendResult:
    sent_at = datetime.fromisoformat(str(payload["sent_at"]))
    return InboxSendResult(
        UUID(str(payload["command_id"])),
        tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        str(payload["from"]),
        UUID(str(payload["message_id"])),
        int(cast(int, payload["position"])),
        sent_at,
        UUID(str(payload["thread_id"])),
        int(cast(int, payload["thread_version"])),
        str(payload["to"]),
    )


def _promotion_result(payload: dict[str, object]) -> InboxPromotionResult:
    event_ids = cast(list[object], payload["event_ids"])
    return InboxPromotionResult(
        UUID(str(payload["command_id"])),
        UUID(str(event_ids[0])),
        UUID(str(payload["thread_id"])),
        int(cast(int, payload["thread_version"])),
        UUID(str(payload["ticket_id"])),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _unavailable(command_id: UUID) -> RecordProblem:
    return _problem(
        command_id,
        "tenant-scope-denied",
        404,
        "The requested inbox thread is unavailable in the authenticated scope.",
    )


def _problem(command_id: UUID, code: str, status: int, detail: str) -> RecordProblem:
    return RecordProblem(code, detail, status, "Inbox command refused", command_id)
