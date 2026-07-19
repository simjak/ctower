"""Atomic Postgres custody transfer transaction for the Record Adapter."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_api._ticket_sql import (
    _canonical_json,
    _result_from_payload,
    _ticket_from_row,
    _timestamp,
    _uuid7,
)
from ctower_kernel.record import (
    Actor,
    CustodyCommand,
    RecordProblem,
    TicketCommandResult,
)

__all__ = ["transfer_custody"]


@dataclass(frozen=True, slots=True)
class _CustodyIds:
    event: UUID
    outbox: UUID


def transfer_custody(
    dsn: str,
    actor: Actor,
    command: CustodyCommand,
    *,
    request_digest: bytes,
    now: datetime,
) -> TicketCommandResult | RecordProblem:
    """Deduplicate, lock, compare, and atomically replace current custody."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        existing = _existing_result(connection, actor, command, request_digest)
        if existing is not None:
            return existing
        ticket_row = _locked_ticket(connection, actor, command.ticket_id)
        if ticket_row is None:
            return _scope_problem(command.client_command_id)
        existing = _existing_result(connection, actor, command, request_digest)
        if existing is not None:
            return existing
        refusal = _transfer_refusal(connection, actor, command, ticket_row)
        if refusal is not None:
            return refusal
        identifiers = _CustodyIds(_uuid7(now), _uuid7(now))
        result = _commit_transfer(
            connection,
            actor,
            command,
            ticket_row,
            identifiers=identifiers,
            request_digest=request_digest,
            now=now,
        )
    return result


def _existing_result(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    request_digest: bytes,
) -> TicketCommandResult | RecordProblem | None:
    row = connection.execute(
        """
        SELECT request_sha256, response_body
        FROM command_results
        WHERE principal_id = %s AND client_command_id = %s
        """,
        (actor.principal_id, command.client_command_id),
    ).fetchone()
    if row is None:
        return None
    stored_digest = bytes(cast(bytes, row["request_sha256"]))
    if not hmac.compare_digest(stored_digest, request_digest):
        return RecordProblem(
            code="idempotency-conflict",
            detail="The command key was already used with a different request body.",
            status=409,
            title="Idempotency conflict",
            command_id=command.client_command_id,
        )
    return _result_from_payload(cast(dict[str, object], row["response_body"]))


def _locked_ticket(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, ticket_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT ticket_id, title, source_kind, source_ref, priority,
            custodian_principal_id, version, created_at
        FROM tickets
        WHERE tenant_id = %s AND ticket_id = %s
        FOR UPDATE
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()


def _transfer_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    ticket_row: dict[str, object],
) -> RecordProblem | None:
    current_version = int(cast(int, ticket_row["version"]))
    current_custodian = cast(UUID, ticket_row["custodian_principal_id"])
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
) -> TicketCommandResult:
    next_version = int(cast(int, ticket_row["version"])) + 1
    _replace_interval(connection, actor, command, next_version=next_version, now=now)
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
    )
    return result


def _replace_interval(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    *,
    next_version: int,
    now: datetime,
) -> None:
    updated = connection.execute(
        """
        UPDATE assignment_intervals
        SET released_at = %s
        WHERE tenant_id = %s AND ticket_id = %s
          AND assignment_kind = 'ticket_custodian' AND released_at IS NULL
          AND principal_id = %s
        """,
        (now, actor.tenant_id, command.ticket_id, command.from_custodian_id),
    )
    if updated.rowcount != 1:
        raise RuntimeError("locked ticket custody interval is inconsistent")
    connection.execute(
        """
        INSERT INTO assignment_intervals (
            ticket_id, tenant_id, interval_sequence, assignment_kind, principal_id,
            assigned_at, released_at, changed_by, reason, client_command_id
        ) VALUES (%s, %s, %s, 'ticket_custodian', %s, %s, NULL, %s, %s, %s)
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
) -> None:
    prev_hash = _previous_hash(connection, actor, command, sequence=sequence)
    payload = _transfer_payload(command)
    event_hash = _event_hash(
        actor, command, identifiers, request_digest, payload, prev_hash, sequence, now
    )
    _insert_event(
        connection,
        actor,
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        payload=payload,
        prev_hash=prev_hash,
        event_hash=event_hash,
        sequence=sequence,
        now=now,
    )
    _insert_result_and_outbox(
        connection,
        actor,
        command,
        result,
        identifiers=identifiers,
        request_digest=request_digest,
        payload=payload,
        now=now,
    )


def _previous_hash(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    *,
    sequence: int,
) -> bytes:
    row = connection.execute(
        """
        SELECT event_hash
        FROM events
        WHERE tenant_id = %s AND aggregate_id = %s AND sequence = %s
        """,
        (actor.tenant_id, command.ticket_id, sequence - 1),
    ).fetchone()
    if row is None:
        raise RuntimeError("locked ticket event stream is inconsistent")
    return bytes(cast(bytes, row["event_hash"]))


def _transfer_payload(command: CustodyCommand) -> dict[str, object]:
    return {
        "from_custodian_id": str(command.from_custodian_id),
        "reason": command.reason,
        "to_custodian_id": str(command.to_custodian_id),
    }


def _insert_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    *,
    identifiers: _CustodyIds,
    request_digest: bytes,
    payload: dict[str, object],
    prev_hash: bytes,
    event_hash: bytes,
    sequence: int,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind, schema_version,
            actor_principal_id, client_command_id, request_sha256, correlation_id,
            causation_id, origin, server_time, payload, prev_hash, event_hash
        ) VALUES (%s, %s, %s, %s, %s, 'ticket.custody_transferred', 1, %s, %s, %s,
            %s, NULL, 'api', %s, %s, %s, %s)
        """,
        (
            identifiers.event,
            actor.tenant_id,
            f"ticket/{command.ticket_id}",
            command.ticket_id,
            sequence,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            command.client_command_id,
            now,
            Jsonb(payload),
            prev_hash,
            event_hash,
        ),
    )


def _insert_result_and_outbox(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: CustodyCommand,
    result: TicketCommandResult,
    *,
    identifiers: _CustodyIds,
    request_digest: bytes,
    payload: dict[str, object],
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO command_results (
            tenant_id, principal_id, client_command_id, request_sha256, status_code,
            response_body, event_ids, created_at
        ) VALUES (%s, %s, %s, %s, 200, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            Jsonb(result.response_payload()),
            [identifiers.event],
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO outbox (outbox_id, tenant_id, event_id, topic, payload, created_at)
        VALUES (%s, %s, %s, 'record.events', %s, %s)
        """,
        (identifiers.outbox, actor.tenant_id, identifiers.event, Jsonb(payload), now),
    )


def _event_hash(
    actor: Actor,
    command: CustodyCommand,
    identifiers: _CustodyIds,
    request_digest: bytes,
    payload: dict[str, object],
    prev_hash: bytes,
    sequence: int,
    now: datetime,
) -> bytes:
    material: dict[str, object] = {
        "actor_principal_id": str(actor.principal_id),
        "aggregate_id": str(command.ticket_id),
        "causation_id": None,
        "client_command_id": str(command.client_command_id),
        "correlation_id": str(command.client_command_id),
        "event_id": str(identifiers.event),
        "kind": "ticket.custody_transferred",
        "origin": "api",
        "payload": payload,
        "prev_hash": f"sha256:{prev_hash.hex()}",
        "request_sha256": f"sha256:{request_digest.hex()}",
        "schema_version": 1,
        "sequence": sequence,
        "server_time": _timestamp(now),
        "stream_id": f"ticket/{command.ticket_id}",
        "tenant_id": str(actor.tenant_id),
    }
    return hashlib.sha256(_canonical_json(material)).digest()


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
