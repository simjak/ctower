"""Record-owned Postgres ticket append, replay, and tenant-scoped reads."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
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
from ctower_kernel.record._commands import reserve_command
from ctower_kernel.record._event_store import append_event, enqueue_event
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    TicketCreatedPayload,
    ticket_payload_from_mapping,
)
from ctower_kernel.telemetry import TelemetryContext

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
    telemetry: TelemetryContext,
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
            telemetry=telemetry,
        )
    return result


def get_ticket(
    dsn: str, actor: Actor, ticket_id: UUID, *, telemetry: TelemetryContext
) -> Ticket | RecordProblem:
    """Read one ticket using a tenant predicate that reveals no foreign existence."""

    del telemetry
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


def ticket_timeline(
    dsn: str, actor: Actor, ticket_id: UUID, *, telemetry: TelemetryContext
) -> TicketTimeline | RecordProblem:
    """Read an ordered event stream using the same no-disclosure tenant predicate."""

    del telemetry
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        rows = connection.execute(
            """
            SELECT event_id, sequence, kind, actor_principal_id, client_command_id,
                server_time, payload
            FROM events
            WHERE tenant_id = %s AND aggregate_id = %s
              AND kind IN ('ticket.created', 'ticket.custody_transferred')
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
    outcome = reserve_command(
        connection,
        actor.principal_id,
        command.client_command_id,
        request_digest,
    )
    if outcome is None or isinstance(outcome, RecordProblem):
        return outcome
    return _result_from_payload(outcome)


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
    telemetry: TelemetryContext,
) -> None:
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=identifiers.ticket,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=identifiers.event,
        kind=EventKind.TICKET_CREATED,
        origin=EventOrigin.API,
        payload=TicketCreatedPayload(
            custodian_id=command.initial_custodian_id,
            priority=command.priority,
            source_kind=command.source.kind,
            source_ref=command.source.ref,
            title=command.title,
        ),
        prev_hash=ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"ticket:{identifiers.ticket}",
        tenant_id=actor.tenant_id,
    )
    append_event(connection, event, subjects=(("ticket", identifiers.ticket),))
    _insert_result_and_outbox(
        connection,
        actor,
        command,
        result,
        identifiers=identifiers,
        request_digest=request_digest,
        event=event,
        telemetry=telemetry,
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
    event: EventEnvelope,
    telemetry: TelemetryContext,
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
    enqueue_event(
        connection,
        identifiers.outbox,
        event,
        telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command.client_command_id),
            ticket_id=str(identifiers.ticket),
        ),
        now,
    )


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
    kind = EventKind(str(row["kind"]))
    payload = cast(dict[str, object], row["payload"])
    return TimelineEvent(
        actor_principal_id=cast(UUID, row["actor_principal_id"]),
        command_id=cast(UUID, row["client_command_id"]),
        event_id=cast(UUID, row["event_id"]),
        kind=kind,
        occurred_at=cast(datetime, row["server_time"]),
        payload=ticket_payload_from_mapping(kind, payload),
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
