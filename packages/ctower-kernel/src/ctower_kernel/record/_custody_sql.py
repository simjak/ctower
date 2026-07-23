"""Atomic Postgres custody transfer transaction for the Record Adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import (
    Actor,
    CustodyCommand,
    RecordProblem,
    TicketCommandResult,
)
from ctower_kernel.record._ticket_sql import (
    _result_from_payload,
    _ticket_from_row,
    _uuid7,
)
from ctower_kernel.record.events import (
    CustodyTransferredPayload,
    EventEnvelope,
    EventKind,
    EventOrigin,
)
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["transfer_custody"]


@dataclass(frozen=True, slots=True)
class _CustodyIds:
    event: UUID
    outbox: UUID


@dataclass(frozen=True, slots=True)
class _PreviousEvent:
    event_hash: bytes
    event_id: UUID
    correlation_id: UUID


def transfer_custody(
    dsn: str,
    actor: Actor,
    command: CustodyCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> TicketCommandResult | RecordProblem:
    """Deduplicate, lock, compare, and atomically replace current custody."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        existing = transaction.reserve(
            actor.principal_id, command.client_command_id, request_digest
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
        ticket_row = _locked_ticket(connection, actor, command.ticket_id)
        if ticket_row is None:
            problem = _scope_problem(command.client_command_id)
            return _refuse(transaction, actor, command, request_digest, problem, now)
        refusal = _transfer_refusal(connection, actor, command, ticket_row)
        if refusal is not None:
            return _refuse(transaction, actor, command, request_digest, refusal, now)
        identifiers = _CustodyIds(_uuid7(now), _uuid7(now))
        result = _commit_transfer(
            connection,
            actor,
            command,
            ticket_row,
            identifiers=identifiers,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
    return result


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: CustodyCommand,
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


def _locked_ticket(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, ticket_id: UUID
) -> dict[str, object] | None:
    ticket = connection.execute(
        """
        SELECT ticket_id, title, source_kind, source_ref, priority,
            custodian_principal_id, version, created_at, current_episode
        FROM tickets WHERE tenant_id = %s AND ticket_id = %s
        FOR UPDATE
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()
    if ticket is None:
        return None
    lifecycle = cast(
        dict[str, object],
        connection.execute(
            """
            SELECT state FROM lifecycle_episodes
            WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s
            """,
            (actor.tenant_id, ticket_id, ticket["current_episode"]),
        ).fetchone(),
    )
    return {**ticket, "lifecycle_state": lifecycle["state"]}


def _transfer_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    ticket_row: dict[str, object],
) -> RecordProblem | None:
    current_version = int(cast(int, ticket_row["version"]))
    current_custodian = cast(UUID, ticket_row["custodian_principal_id"])
    if str(ticket_row["lifecycle_state"]) in {"closed", "cancelled"}:
        return _version_problem(
            command, current_version, "Closed ticket custody cannot be transferred."
        )
    if command.expected_version != current_version:
        return _version_problem(command, current_version, "The expected ticket version is stale.")
    if command.from_custodian_id != current_custodian:
        return _version_problem(
            command, current_version, "The declared current custodian is stale."
        )
    if not _eligible_target(connection, actor, command.to_custodian_id):
        return _scope_problem(command.client_command_id)
    if command.to_custodian_id == current_custodian:
        return _version_problem(
            command, current_version, "Custody already belongs to that principal."
        )
    return None


def _eligible_target(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, principal_id: UUID
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM principals
        WHERE tenant_id = %s AND principal_id = %s AND NOT disabled
          AND kind IN ('commander', 'operator')
        """,
        (actor.tenant_id, principal_id),
    ).fetchone()
    return row is not None


def _commit_transfer(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    ticket_row: dict[str, object],
    *,
    identifiers: _CustodyIds,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> TicketCommandResult:
    next_version = int(cast(int, ticket_row["version"])) + 1
    _replace_interval(
        connection,
        actor,
        command,
        episode=int(cast(int, ticket_row["current_episode"])),
        next_version=next_version,
        now=now,
    )
    connection.execute(
        """
        UPDATE tickets
        SET custodian_principal_id = %s, version = %s
        WHERE tenant_id = %s AND ticket_id = %s
        """,
        (command.to_custodian_id, next_version, actor.tenant_id, command.ticket_id),
    )
    ticket = _ticket_from_row(
        {
            **ticket_row,
            "custodian_principal_id": command.to_custodian_id,
            "version": next_version,
        }
    )
    result = TicketCommandResult(command.client_command_id, (identifiers.event,), ticket)
    _append_transfer(
        connection,
        actor,
        command,
        result,
        identifiers=identifiers,
        request_digest=request_digest,
        sequence=next_version,
        now=now,
        telemetry=telemetry,
    )
    return result


def _replace_interval(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    *,
    episode: int,
    next_version: int,
    now: datetime,
) -> None:
    updated = connection.execute(
        """
        UPDATE assignment_intervals
        SET released_at = %s
        WHERE tenant_id = %s AND ticket_id = %s
          AND assignment_kind = 'ticket_custodian' AND released_at IS NULL
          AND principal_id = %s AND episode_number = %s
        """,
        (now, actor.tenant_id, command.ticket_id, command.from_custodian_id, episode),
    )
    if updated.rowcount != 1:
        raise RuntimeError("locked ticket custody interval is inconsistent")
    connection.execute(
        """
        INSERT INTO assignment_intervals (
            ticket_id, tenant_id, interval_sequence, assignment_kind, principal_id,
            assigned_at, released_at, changed_by, reason, client_command_id, episode_number
        ) VALUES (%s, %s, %s, 'ticket_custodian', %s, %s, NULL, %s, %s, %s, %s)
        """,
        (
            command.ticket_id,
            actor.tenant_id,
            next_version,
            command.to_custodian_id,
            now,
            actor.principal_id,
            command.reason,
            command.client_command_id,
            episode,
        ),
    )


def _append_transfer(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    result: TicketCommandResult,
    *,
    identifiers: _CustodyIds,
    request_digest: bytes,
    sequence: int,
    now: datetime,
    telemetry: TelemetryContext,
) -> None:
    previous = _previous_event(connection, actor, command, sequence=sequence)
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.ticket_id,
        causation_id=previous.event_id,
        client_command_id=command.client_command_id,
        correlation_id=previous.correlation_id,
        event_id=identifiers.event,
        kind=EventKind.CUSTODY_TRANSFERRED,
        origin=EventOrigin.API,
        payload=CustodyTransferredPayload(
            from_custodian_id=command.from_custodian_id,
            reason=command.reason,
            to_custodian_id=command.to_custodian_id,
        ),
        prev_hash=previous.event_hash,
        request_sha256=request_digest,
        sequence=sequence,
        server_time=now,
        stream_id=f"ticket:{command.ticket_id}",
        tenant_id=actor.tenant_id,
    )
    RecordTransaction(connection).commit(
        event,
        outbox_id=identifiers.outbox,
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


def _previous_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    *,
    sequence: int,
) -> _PreviousEvent:
    row = connection.execute(
        """
        SELECT event_hash, event_id, correlation_id
        FROM events
        WHERE tenant_id = %s AND aggregate_id = %s AND sequence = %s
        """,
        (actor.tenant_id, command.ticket_id, sequence - 1),
    ).fetchone()
    if row is None:
        raise RuntimeError("locked ticket event stream is inconsistent")
    return _PreviousEvent(
        event_hash=bytes(cast(bytes, row["event_hash"])),
        event_id=cast(UUID, row["event_id"]),
        correlation_id=cast(UUID, row["correlation_id"]),
    )


def _version_problem(command: CustodyCommand, current: int, detail: str) -> RecordProblem:
    return RecordProblem(
        code="version-conflict",
        detail=detail,
        status=409,
        title="Ticket version conflict",
        command_id=command.client_command_id,
        current_version=current,
    )


def _scope_problem(command_id: UUID) -> RecordProblem:
    return RecordProblem(
        code="tenant-scope-denied",
        detail="The requested ticket is unavailable in the authenticated tenant scope.",
        status=404,
        title="Ticket unavailable",
        command_id=command_id,
    )
