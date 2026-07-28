"""Record-owned authenticated ticket-comment append and exact replay."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record._uuid import uuid7 as _uuid7
from ctower_kernel.record.comments import (
    TicketCommentCommand,
    TicketCommentResult,
    ticket_accepts_comments,
)
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    TicketCommentAddedPayload,
)
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def add_comment(
    dsn: str,
    actor: Actor,
    command: TicketCommentCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> TicketCommentResult | RecordProblem:
    """Reserve before lookup, serialize the ticket stream, and append one comment."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id,
            command.client_command_id,
            request_digest,
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _result_from_payload(existing)
        pending = transaction.require_durable_subjects(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (("ticket", command.ticket_id),),
            now=now,
        )
        if pending is not None:
            return pending
        ticket = _locked_ticket(connection, actor, command.ticket_id)
        if ticket is None:
            problem = _problem(
                command,
                "tenant-scope-denied",
                404,
                "Ticket unavailable",
            )
            return _refuse(transaction, actor, command, request_digest, problem, now)
        ineligibility = _comment_ineligibility(command, ticket["state"])
        if ineligibility is not None:
            return _refuse(transaction, actor, command, request_digest, ineligibility, now)
        result = _append_comment(
            connection,
            actor,
            command,
            ticket,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
    return result


def _comment_ineligibility(
    command: TicketCommentCommand,
    state: object,
) -> RecordProblem | None:
    if ticket_accepts_comments(str(state)):
        return None
    return _problem(
        command,
        "ticket-comment-ineligible",
        409,
        "Terminal ticket comment refused",
    )


def _locked_ticket(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    ticket_id: UUID,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT ticket.version, episode.state
        FROM tickets AS ticket
        JOIN lifecycle_episodes AS episode
          ON episode.ticket_id = ticket.ticket_id
         AND episode.episode_number = ticket.current_episode
        WHERE ticket.tenant_id = %s AND ticket.ticket_id = %s
        FOR UPDATE OF ticket
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()


def _append_comment(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommentCommand,
    ticket: dict[str, object],
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> TicketCommentResult:
    next_sequence = int(cast(int, ticket["version"])) + 1
    previous = connection.execute(
        """
        SELECT event_id, event_hash
        FROM events
        WHERE tenant_id = %s AND stream_id = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, f"ticket:{command.ticket_id}"),
    ).fetchone()
    if previous is None:
        raise RuntimeError("locked ticket event stream is inconsistent")
    comment_id, event_id, outbox_id = (_uuid7(now) for _ in range(3))
    result = TicketCommentResult(
        command_id=command.client_command_id,
        comment_id=comment_id,
        event_id=event_id,
        ticket_id=command.ticket_id,
    )
    connection.execute(
        "UPDATE tickets SET version = %s WHERE tenant_id = %s AND ticket_id = %s",
        (next_sequence, actor.tenant_id, command.ticket_id),
    )
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.ticket_id,
        causation_id=cast(UUID, previous["event_id"]),
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.TICKET_COMMENT_ADDED,
        origin=EventOrigin.API,
        payload=TicketCommentAddedPayload(
            body=command.body,
            comment_id=comment_id,
            ticket_id=command.ticket_id,
        ),
        prev_hash=bytes(cast(bytes, previous["event_hash"])),
        request_sha256=request_digest,
        sequence=next_sequence,
        server_time=now,
        stream_id=f"ticket:{command.ticket_id}",
        tenant_id=actor.tenant_id,
    )
    RecordTransaction(connection).commit(
        event,
        outbox_id=outbox_id,
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command.client_command_id),
            ticket_id=str(command.ticket_id),
        ),
        now=now,
        subjects=(("ticket", command.ticket_id),),
    )
    return result


def _result_from_payload(payload: dict[str, object]) -> TicketCommentResult:
    return TicketCommentResult(
        command_id=UUID(str(payload["command_id"])),
        comment_id=UUID(str(payload["comment_id"])),
        event_id=UUID(str(payload["event_id"])),
        ticket_id=UUID(str(payload["ticket_id"])),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: TicketCommentCommand,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _problem(
    command: TicketCommentCommand,
    code: str,
    status: int,
    title: str,
) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=command.client_command_id,
    )
