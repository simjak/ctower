"""Record-owned SQL for append-only native-inbox delivery and read facts."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.inbox._delivery_events import _acknowledgement_events
from ctower_kernel.inbox.models import (
    InboxAcknowledgeCommand,
    InboxAcknowledgementState,
    InboxAcknowledgeResult,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin, event_digest
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.inbox_events import (
    InboxMessageDeliveredPayload,
    InboxMessageReadPayload,
    InboxParticipant,
)
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def acknowledge_message(
    dsn: str,
    actor: Actor,
    command: InboxAcknowledgeCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxAcknowledgeResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _acknowledge_result(replay)
        return _advance_acknowledgement(
            connection, transaction, actor, command, request_digest, now, telemetry
        )


def _advance_acknowledgement(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: InboxAcknowledgeCommand,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxAcknowledgeResult | RecordProblem:
    message = _lock_message(connection, actor.tenant_id, command.message_id)
    problem = _acknowledgement_problem(actor, command, message)
    if problem is not None:
        return _refuse(transaction, actor, command.client_command_id, request_digest, problem, now)
    locked = cast(dict[str, object], message)
    thread_id = cast(UUID, locked["thread_id"])
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
    facts = _facts(connection, actor.tenant_id, command.message_id)
    if command.state.value in facts or (
        command.state is InboxAcknowledgementState.DELIVERED and "read" in facts
    ):
        return _refuse(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            _problem(
                command.client_command_id,
                "inbox-acknowledgement-not-advancing",
                409,
                "The requested acknowledgement does not advance message delivery state.",
            ),
            now,
        )
    recipient = InboxParticipant(cast(UUID, locked["recipient_id"]), str(locked["recipient_seat"]))
    events = _acknowledgement_events(
        actor,
        command,
        recipient,
        thread_id=thread_id,
        first_sequence=int(cast(int, locked["version"])) + 1,
        previous_hash=bytes(cast(bytes, locked["last_event_hash"])),
        include_delivered="delivered" not in facts,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    result = _result(command, thread_id, events, facts, now)
    transaction.commit_batch(
        tuple(EventCommit(event, uuid7(now)) for event in events),
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry,
        now=now,
        subjects=(("inbox_thread", thread_id),),
    )
    _persist(connection, actor, command, result, events)
    return result


def _lock_message(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, message_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT m.thread_id, m.recipient_id, m.recipient_seat,
               t.participant_a_id, t.participant_b_id, t.version, t.last_event_hash
        FROM inbox_messages AS m
        JOIN inbox_threads AS t
          ON t.tenant_id = m.tenant_id AND t.thread_id = m.thread_id
        WHERE m.tenant_id = %s AND m.message_id = %s
        FOR UPDATE OF t
        """,
        (tenant_id, message_id),
    ).fetchone()


def _acknowledgement_problem(
    actor: Actor,
    command: InboxAcknowledgeCommand,
    message: dict[str, object] | None,
) -> RecordProblem | None:
    if message is None or actor.principal_id not in {
        message.get("participant_a_id"),
        message.get("participant_b_id"),
    }:
        return _unavailable(command.client_command_id)
    if actor.principal_id != message.get("recipient_id") and not (
        actor.kind is PrincipalKind.OPERATOR
        and command.origin in {EventOrigin.MIGRATION_IMPORTER, EventOrigin.ESTATE_IMPORT}
    ):
        return _problem(
            command.client_command_id,
            "inbox-message-recipient-mismatch",
            403,
            "Only the recorded recipient may acknowledge an inbox message.",
        )
    return None


def _facts(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, message_id: UUID
) -> dict[str, tuple[UUID, datetime]]:
    rows = connection.execute(
        """
        SELECT state, event_id, recorded_at FROM inbox_message_delivery_facts
        WHERE tenant_id = %s AND message_id = %s
        """,
        (tenant_id, message_id),
    ).fetchall()
    return {
        str(row["state"]): (cast(UUID, row["event_id"]), cast(datetime, row["recorded_at"]))
        for row in rows
    }


def _result(
    command: InboxAcknowledgeCommand,
    thread_id: UUID,
    events: tuple[EventEnvelope, ...],
    facts: dict[str, tuple[UUID, datetime]],
    now: datetime,
) -> InboxAcknowledgeResult:
    recorded_at = command.recorded_at or now
    delivered_at = facts.get("delivered", (events[0].event_id, recorded_at))[1]
    return InboxAcknowledgeResult(
        command.client_command_id,
        delivered_at,
        tuple(event.event_id for event in events),
        command.message_id,
        recorded_at if command.state is InboxAcknowledgementState.READ else None,
        command.state,
        thread_id,
        events[-1].sequence,
    )


def _persist(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxAcknowledgeCommand,
    result: InboxAcknowledgeResult,
    events: tuple[EventEnvelope, ...],
) -> None:
    for event in events:
        state = (
            InboxAcknowledgementState.DELIVERED
            if event.kind is EventKind.INBOX_MESSAGE_DELIVERED
            else InboxAcknowledgementState.READ
        )
        recipient = cast(
            InboxMessageDeliveredPayload | InboxMessageReadPayload, event.payload
        ).recipient
        connection.execute(
            """
            INSERT INTO inbox_message_delivery_facts (
                event_id, tenant_id, thread_id, message_id, recipient_id,
                recipient_seat, state, recorded_by, recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.event_id,
                actor.tenant_id,
                result.thread_id,
                result.message_id,
                recipient.principal_id,
                recipient.seat_key,
                state.value,
                actor.principal_id,
                command.recorded_at or event.server_time,
            ),
        )
    connection.execute(
        """
        UPDATE inbox_threads SET version = %s, last_event_hash = %s
        WHERE tenant_id = %s AND thread_id = %s
        """,
        (result.thread_version, event_digest(events[-1]), actor.tenant_id, result.thread_id),
    )


def _acknowledge_result(payload: dict[str, object]) -> InboxAcknowledgeResult:
    read_at = payload.get("read_at")
    return InboxAcknowledgeResult(
        UUID(str(payload["command_id"])),
        datetime.fromisoformat(str(payload["delivered_at"])),
        tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        UUID(str(payload["message_id"])),
        datetime.fromisoformat(str(read_at)) if read_at is not None else None,
        InboxAcknowledgementState(str(payload["state"])),
        UUID(str(payload["thread_id"])),
        int(cast(int, payload["thread_version"])),
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
        actor.tenant_id, actor.principal_id, command_id, request_digest, problem, now=now
    )
    return problem


def _unavailable(command_id: UUID) -> RecordProblem:
    return _problem(
        command_id,
        "tenant-scope-denied",
        404,
        "The requested inbox message is unavailable in the authenticated scope.",
    )


def _problem(command_id: UUID, code: str, status: int, detail: str) -> RecordProblem:
    return RecordProblem(code, detail, status, "Inbox command refused", command_id)
