"""Board-context-owned authenticated Change-reference append and exact replay."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.board_context.change_references import (
    ChangeReferenceCommand,
    ChangeReferenceResult,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.context_set_events import ChangeReferenceRecordedPayload
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def record_change_reference(
    dsn: str,
    actor: Actor,
    command: ChangeReferenceCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> ChangeReferenceResult | RecordProblem:
    """Reserve before lookup, serialize the ticket stream, and append one Change fact."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        existing = transaction.reserve_ticket_mutation(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (command.ticket_id,),
            now=now,
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
        problem = _refusal(connection, transaction, actor, command, request_digest, now)
        if problem is not None:
            return problem
        ticket = _locked_ticket(connection, actor, command.ticket_id)
        if ticket is None:
            raise RuntimeError("locked ticket disappeared after refusal check")
        return _append(
            connection,
            actor,
            command,
            ticket,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _refusal(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: ChangeReferenceCommand,
    request_digest: bytes,
    now: datetime,
) -> RecordProblem | None:
    problem: RecordProblem | None = None
    if _locked_ticket(connection, actor, command.ticket_id) is None:
        problem = RecordProblem(
            code="tenant-scope-denied",
            detail="Ticket unavailable",
            status=404,
            title="Ticket unavailable",
            command_id=command.client_command_id,
        )
    elif _already_linked(connection, actor, command):
        problem = RecordProblem(
            code="change-reference-duplicate",
            detail="This repository and change identity are already linked to the ticket.",
            status=409,
            title="Change reference already recorded",
            command_id=command.client_command_id,
        )
    if problem is not None:
        transaction.refuse(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            problem,
            now=now,
        )
    return problem


def _locked_ticket(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    ticket_id: UUID,
) -> dict[str, object] | None:
    return connection.execute(
        "SELECT version FROM tickets WHERE tenant_id = %s AND ticket_id = %s FOR UPDATE",
        (actor.tenant_id, ticket_id),
    ).fetchone()


def _already_linked(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ChangeReferenceCommand,
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM ticket_change_references
        WHERE tenant_id = %s AND ticket_id = %s AND repository = %s AND change_identity = %s
        """,
        (actor.tenant_id, command.ticket_id, command.repository, command.change_identity),
    ).fetchone()
    return row is not None


def _append(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ChangeReferenceCommand,
    ticket: dict[str, object],
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> ChangeReferenceResult:
    next_sequence = int(cast(int, ticket["version"])) + 1
    previous = _previous_event(connection, actor, command.ticket_id)
    change_reference_id, event_id, outbox_id = (_uuid7(now) for _ in range(3))
    result = ChangeReferenceResult(
        command_id=command.client_command_id,
        change_reference_id=change_reference_id,
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
        kind=EventKind.CHANGE_REFERENCE_RECORDED,
        origin=EventOrigin.API,
        payload=ChangeReferenceRecordedPayload(
            change_reference_id=change_reference_id,
            ticket_id=command.ticket_id,
            repository=command.repository,
            change_identity=command.change_identity,
            reference=command.reference,
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
    _insert_change_reference(connection, actor, command, change_reference_id, event_id, now)
    return result


def _previous_event(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, ticket_id: UUID
) -> dict[str, object]:
    previous = connection.execute(
        """
        SELECT event_id, event_hash FROM events
        WHERE tenant_id = %s AND stream_id = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, f"ticket:{ticket_id}"),
    ).fetchone()
    if previous is None:
        raise RuntimeError("locked ticket event stream is inconsistent")
    return previous


def _insert_change_reference(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ChangeReferenceCommand,
    change_reference_id: UUID,
    event_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO ticket_change_references (
            change_reference_id, tenant_id, ticket_id, repository, change_identity,
            reference, event_id, actor_principal_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            change_reference_id,
            actor.tenant_id,
            command.ticket_id,
            command.repository,
            command.change_identity,
            command.reference,
            event_id,
            actor.principal_id,
            now,
        ),
    )


def _result_from_payload(payload: dict[str, object]) -> ChangeReferenceResult:
    return ChangeReferenceResult(
        command_id=UUID(str(payload["command_id"])),
        change_reference_id=UUID(str(payload["change_reference_id"])),
        event_id=UUID(str(payload["event_id"])),
        ticket_id=UUID(str(payload["ticket_id"])),
    )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
