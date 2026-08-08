"""Pair-grouped notification ingestion on the native Inbox authority."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID, uuid5

import psycopg

from ctower_kernel.inbox._sql import (
    _lock_thread,
    _message_commits,
    _persist_message,
    _problem,
    _refuse,
    _send_result,
    _thread_participants,
    _validate_send,
)
from ctower_kernel.inbox.models import InboxSendCommand, InboxSendResult
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.inbox_events import InboxParticipant
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def ingest_notification(
    dsn: str,
    actor: Actor,
    command: InboxSendCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxSendResult | RecordProblem:
    """Open or append the one deterministic notification thread for an unordered seat pair."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _send_result(replay)
        return _ingest_reserved(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _ingest_reserved(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: InboxSendCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> InboxSendResult | RecordProblem:
    pair = _notification_participants(connection, actor, command)
    if isinstance(pair, RecordProblem):
        return _refuse(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            pair,
            now,
        )
    sender, recipient = pair
    thread_id = _pair_thread_id(actor.tenant_id, sender.principal_id, recipient.principal_id)
    _lock_pair_identity(connection, actor.tenant_id, thread_id)
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
    thread = _notification_thread(connection, actor, command, sender, recipient, thread_id)
    if isinstance(thread, RecordProblem):
        return _refuse(
            transaction,
            actor,
            command.client_command_id,
            request_digest,
            thread,
            now,
        )
    return _commit_notification(
        connection,
        transaction,
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


def _notification_participants(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxSendCommand,
) -> tuple[InboxParticipant, InboxParticipant] | RecordProblem:
    if command.thread_id is not None:
        return _problem(
            command.client_command_id,
            "invalid-request",
            422,
            "Notification ingestion derives its thread from authenticated participants.",
        )
    validation = _validate_send(connection, actor, command)
    if isinstance(validation, RecordProblem):
        return validation
    sender, recipient, _unused_thread = validation
    return sender, recipient


def _notification_thread(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: InboxSendCommand,
    sender: InboxParticipant,
    recipient: InboxParticipant,
    thread_id: UUID,
) -> dict[str, object] | RecordProblem | None:
    thread = _lock_thread(connection, actor.tenant_id, thread_id)
    if thread is None:
        return None
    participants = _thread_participants(thread)
    if {item.principal_id for item in participants} != {
        sender.principal_id,
        recipient.principal_id,
    }:
        return _problem(
            command.client_command_id,
            "inbox-thread-participant-mismatch",
            409,
            "The notification thread belongs to another seat pair.",
        )
    thread["next_position"] = _next_position(connection, actor.tenant_id, thread_id)
    return thread


def _commit_notification(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
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
) -> InboxSendResult:
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


def _pair_thread_id(tenant_id: UUID, first: UUID, second: UUID) -> UUID:
    pair = ":".join(sorted((str(first), str(second))))
    return uuid5(tenant_id, f"inbox-notification-pair:{pair}")


def _lock_pair_identity(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    thread_id: UUID,
) -> None:
    identity = f"{tenant_id}:inbox_thread:{thread_id}"
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (identity,),
    )


def _next_position(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    thread_id: UUID,
) -> int:
    row = cast(
        dict[str, object],
        connection.execute(
            """
            SELECT COALESCE(max(position) + 1, 1) AS next_position
            FROM inbox_messages
            WHERE tenant_id = %s AND thread_id = %s
            """,
            (tenant_id, thread_id),
        ).fetchone(),
    )
    return int(cast(int, row["next_position"]))
