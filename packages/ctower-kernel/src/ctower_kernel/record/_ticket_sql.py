"""Record-owned Postgres ticket append, replay, and tenant-scoped reads."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_kernel.record import (
    Actor,
    PrincipalKind,
    RecordProblem,
    SourceReference,
    Ticket,
    TicketCommand,
    TicketCommandResult,
    TicketTimeline,
    TimelineEvent,
)

__all__ = ["actor_for_credential", "create_ticket", "get_ticket", "ticket_timeline"]

ZERO_HASH = bytes(32)


@dataclass(frozen=True, slots=True)
class _TicketIds:
    ticket: UUID
    event: UUID
    outbox: UUID


def actor_for_credential(dsn: str, credential_digest: bytes) -> Actor | None:
    """Resolve an active operator or Commander under service-role grants."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT p.principal_id, p.tenant_id, p.kind
            FROM principal_credentials AS c
            JOIN principals AS p
              ON p.principal_id = c.principal_id AND p.tenant_id = c.tenant_id
            WHERE c.credential_digest = %s AND c.revoked_at IS NULL AND NOT p.disabled
              AND p.kind IN ('operator', 'commander')
            """,
            (credential_digest,),
        ).fetchone()
    if row is None:
        return None
    return Actor(
        principal_id=cast(UUID, row["principal_id"]),
        tenant_id=cast(UUID, row["tenant_id"]),
        kind=PrincipalKind(str(row["kind"])),
    )


def create_ticket(
    dsn: str,
    actor: Actor,
    command: TicketCommand,
    *,
    request_digest: bytes,
    now: datetime,
) -> TicketCommandResult | RecordProblem:
    """Deduplicate before validation and atomically append a new ticket."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        existing = _existing_result(connection, actor, command, request_digest)
        if existing is not None:
            return existing
        if not _eligible_custodian(connection, actor, command.initial_custodian_id):
            return _scope_problem(command.client_command_id)
        identifiers = _TicketIds(*(_uuid7(now) for _ in range(3)))
        ticket = Ticket(
            ticket_id=identifiers.ticket,
            title=command.title,
            source=command.source,
            priority=command.priority,
            custodian_id=command.initial_custodian_id,
            version=1,
            created_at=now,
        )
        result = TicketCommandResult(command.client_command_id, (identifiers.event,), ticket)
        _insert_ticket_state(connection, actor, command, identifiers=identifiers, now=now)
        _append_ticket_created(
            connection,
            actor,
            command,
            result,
            identifiers=identifiers,
            request_digest=request_digest,
            now=now,
        )
    return result


def get_ticket(dsn: str, actor: Actor, ticket_id: UUID) -> Ticket | RecordProblem:
    """Read one ticket using a tenant predicate that reveals no foreign existence."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            """
            SELECT ticket_id, title, source_kind, source_ref, priority,
                custodian_principal_id, version, created_at
            FROM tickets
            WHERE tenant_id = %s AND ticket_id = %s
            """,
            (actor.tenant_id, ticket_id),
        ).fetchone()
    return _ticket_from_row(row) if row is not None else _scope_problem()


def ticket_timeline(dsn: str, actor: Actor, ticket_id: UUID) -> TicketTimeline | RecordProblem:
    """Read an ordered event stream using the same no-disclosure tenant predicate."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        rows = connection.execute(
            """
            SELECT event_id, sequence, kind, actor_principal_id, client_command_id,
                server_time, payload
            FROM events
            WHERE tenant_id = %s AND aggregate_id = %s
            ORDER BY sequence
            """,
            (actor.tenant_id, ticket_id),
        ).fetchall()
    if not rows:
        return _scope_problem()
    events = tuple(_timeline_event(row) for row in rows)
    return TicketTimeline(ticket_id, events)


def _existing_result(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
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


def _eligible_custodian(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, custodian_id: UUID
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM principals
        WHERE tenant_id = %s AND principal_id = %s AND NOT disabled
          AND kind IN ('commander', 'operator')
        """,
        (actor.tenant_id, custodian_id),
    ).fetchone()
    return row is not None


def _insert_ticket_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    *,
    identifiers: _TicketIds,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO tickets (
            ticket_id, tenant_id, title, source_kind, source_ref, priority,
            custodian_principal_id, version, durability_state, created_by, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 'durability_pending', %s, %s)
        """,
        (
            identifiers.ticket,
            actor.tenant_id,
            command.title,
            command.source.kind,
            command.source.ref,
            command.priority,
            command.initial_custodian_id,
            actor.principal_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO lifecycle_episodes (
            ticket_id, tenant_id, episode_number, state, opened_at
        ) VALUES (%s, %s, 1, 'open', %s)
        """,
        (identifiers.ticket, actor.tenant_id, now),
    )
    _insert_initial_custody(connection, actor, command, identifiers=identifiers, now=now)
    _insert_initial_priority(connection, actor, command, identifiers=identifiers, now=now)


def _insert_initial_custody(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    *,
    identifiers: _TicketIds,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO assignment_intervals (
            ticket_id, tenant_id, interval_sequence, assignment_kind, principal_id,
            assigned_at, released_at, changed_by, reason, client_command_id
        ) VALUES (%s, %s, 1, 'ticket_custodian', %s, %s, NULL, %s,
            'initial eligible custodian', %s)
        """,
        (
            identifiers.ticket,
            actor.tenant_id,
            command.initial_custodian_id,
            now,
            actor.principal_id,
            command.client_command_id,
        ),
    )


def _insert_initial_priority(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    *,
    identifiers: _TicketIds,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO priority_facts (
            ticket_id, tenant_id, fact_sequence, priority, changed_by,
            reason, client_command_id, recorded_at
        ) VALUES (%s, %s, 1, %s, %s, 'initial priority', %s, %s)
        """,
        (
            identifiers.ticket,
            actor.tenant_id,
            command.priority,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _append_ticket_created(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    result: TicketCommandResult,
    *,
    identifiers: _TicketIds,
    request_digest: bytes,
    now: datetime,
) -> None:
    payload: dict[str, object] = {
        "custodian_id": str(command.initial_custodian_id),
        "priority": command.priority,
        "source": {"kind": command.source.kind, "ref": command.source.ref},
        "title": command.title,
    }
    event_hash = _ticket_event_hash(
        actor,
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        payload=payload,
        now=now,
    )
    _insert_event(
        connection,
        actor,
        command,
        identifiers=identifiers,
        request_digest=request_digest,
        payload=payload,
        event_hash=event_hash,
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


def _insert_result_and_outbox(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    result: TicketCommandResult,
    *,
    identifiers: _TicketIds,
    request_digest: bytes,
    payload: dict[str, object],
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO command_results (
            tenant_id, principal_id, client_command_id, request_sha256, status_code,
            response_body, event_ids, created_at
        ) VALUES (%s, %s, %s, %s, 201, %s, %s, %s)
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


def _insert_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    *,
    identifiers: _TicketIds,
    request_digest: bytes,
    payload: dict[str, object],
    event_hash: bytes,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO events (
            event_id, tenant_id, stream_id, aggregate_id, sequence, kind, schema_version,
            actor_principal_id, client_command_id, request_sha256, correlation_id,
            causation_id, origin, server_time, payload, prev_hash, event_hash
        ) VALUES (%s, %s, %s, %s, 1, 'ticket.created', 1, %s, %s, %s, %s,
            NULL, 'api', %s, %s, %s, %s)
        """,
        (
            identifiers.event,
            actor.tenant_id,
            f"ticket/{identifiers.ticket}",
            identifiers.ticket,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            command.client_command_id,
            now,
            Jsonb(payload),
            ZERO_HASH,
            event_hash,
        ),
    )


def _ticket_event_hash(
    actor: Actor,
    command: TicketCommand,
    *,
    identifiers: _TicketIds,
    request_digest: bytes,
    payload: dict[str, object],
    now: datetime,
) -> bytes:
    material: dict[str, object] = {
        "actor_principal_id": str(actor.principal_id),
        "aggregate_id": str(identifiers.ticket),
        "causation_id": None,
        "client_command_id": str(command.client_command_id),
        "correlation_id": str(command.client_command_id),
        "event_id": str(identifiers.event),
        "kind": "ticket.created",
        "origin": "api",
        "payload": payload,
        "prev_hash": f"sha256:{ZERO_HASH.hex()}",
        "request_sha256": f"sha256:{request_digest.hex()}",
        "schema_version": 1,
        "sequence": 1,
        "server_time": _timestamp(now),
        "stream_id": f"ticket/{identifiers.ticket}",
        "tenant_id": str(actor.tenant_id),
    }
    return hashlib.sha256(_canonical_json(material)).digest()


def _ticket_from_row(row: dict[str, object]) -> Ticket:
    return Ticket(
        ticket_id=cast(UUID, row["ticket_id"]),
        title=str(row["title"]),
        source=SourceReference(str(row["source_kind"]), str(row["source_ref"])),
        priority=str(row["priority"]),
        custodian_id=cast(UUID, row["custodian_principal_id"]),
        version=int(cast(int, row["version"])),
        created_at=cast(datetime, row["created_at"]),
    )


def _result_from_payload(payload: dict[str, object]) -> TicketCommandResult:
    ticket_payload = cast(dict[str, object], payload["ticket"])
    source_payload = cast(dict[str, object], ticket_payload["source"])
    ticket = Ticket(
        ticket_id=UUID(str(ticket_payload["ticket_id"])),
        title=str(ticket_payload["title"]),
        source=SourceReference(str(source_payload["kind"]), str(source_payload["ref"])),
        priority=str(ticket_payload["priority"]),
        custodian_id=UUID(str(ticket_payload["custodian_id"])),
        version=int(cast(int, ticket_payload["version"])),
        created_at=datetime.fromisoformat(str(ticket_payload["created_at"])),
    )
    event_ids = cast(list[str], payload["event_ids"])
    return TicketCommandResult(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(item) for item in event_ids),
        ticket=ticket,
    )


def _timeline_event(row: dict[str, object]) -> TimelineEvent:
    return TimelineEvent(
        actor_principal_id=cast(UUID, row["actor_principal_id"]),
        command_id=cast(UUID, row["client_command_id"]),
        event_id=cast(UUID, row["event_id"]),
        kind=str(row["kind"]),
        occurred_at=cast(datetime, row["server_time"]),
        payload=cast(dict[str, object], row["payload"]),
        sequence=int(cast(int, row["sequence"])),
    )


def _scope_problem(command_id: UUID | None = None) -> RecordProblem:
    return RecordProblem(
        code="tenant-scope-denied",
        detail="The requested ticket is unavailable in the authenticated tenant scope.",
        status=404,
        title="Ticket unavailable",
        command_id=command_id,
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


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
