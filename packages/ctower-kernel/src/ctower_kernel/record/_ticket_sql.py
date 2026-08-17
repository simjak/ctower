"""Record-owned Postgres ticket append, replay, and tenant-scoped reads."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import (
    Actor,
    DurabilityState,
    RecordProblem,
    SourceReference,
    Ticket,
    TicketCommand,
    TicketCommandResult,
    TicketTimeline,
    TimelineEvent,
)
from ctower_kernel.record.events import EventKind, ticket_payload_from_mapping
from ctower_kernel.record.ticket_creation import (
    TicketCreationIds,
    initial_custody_project,
    insert_ticket_state,
    new_ticket_creation_ids,
    ticket_created_commit,
)
from ctower_kernel.record.transaction import (
    RecordTransaction,
    authority_connection,
    project_scope_refusal,
)
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["create_ticket", "get_ticket", "ticket_timeline"]


def create_ticket(
    dsn: str,
    actor: Actor,
    command: TicketCommand,
    *,
    request_digest: bytes,
    policy_refusal: RecordProblem | None = None,
    now: datetime,
    telemetry: TelemetryContext,
) -> TicketCommandResult | RecordProblem:
    """Deduplicate before validation and atomically append a new ticket."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        identifiers = new_ticket_creation_ids(now)
        project = _prepare_ticket(
            connection,
            transaction,
            actor,
            command,
            identifiers,
            request_digest=request_digest,
            policy_refusal=policy_refusal,
            now=now,
        )
        if not isinstance(project, str):
            return project
        display_key = insert_ticket_state(
            connection,
            actor,
            command,
            project_key=project,
            identifiers=identifiers,
            now=now,
        )
        ticket = Ticket(
            ticket_id=identifiers.ticket,
            title=command.title,
            source=command.source,
            priority=command.priority,
            custodian_id=command.initial_custodian_id,
            version=1,
            created_at=now,
            display_key=display_key,
        )
        result = TicketCommandResult(command.client_command_id, (identifiers.event,), ticket)
        _append_ticket_created(
            connection,
            actor,
            command,
            result,
            project_key=project,
            identifiers=identifiers,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )
    return result


def _prepare_ticket(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: TicketCommand,
    identifiers: TicketCreationIds,
    *,
    request_digest: bytes,
    policy_refusal: RecordProblem | None,
    now: datetime,
) -> str | TicketCommandResult | RecordProblem:
    reserved = _reserve_ticket_outcome(
        transaction,
        actor,
        command,
        request_digest=request_digest,
        policy_refusal=policy_refusal,
        now=now,
    )
    if reserved is not None:
        return reserved
    project = initial_custody_project(
        connection, actor, command.client_command_id, command.initial_custodian_id
    )
    if isinstance(project, RecordProblem):
        return _refuse(transaction, actor, command, request_digest, project, now)
    if command.project_key is not None and command.project_key != project:
        return _refuse(
            transaction,
            actor,
            command,
            request_digest,
            _scope_problem(command.client_command_id),
            now,
        )
    project_refusal = transaction.require_project_mutation(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        project_keys=(project,),
        now=now,
    )
    if project_refusal is not None:
        return project_refusal
    pending = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        (("ticket", identifiers.ticket),),
        now=now,
    )
    return pending if pending is not None else project


def _reserve_ticket_outcome(
    transaction: RecordTransaction,
    actor: Actor,
    command: TicketCommand,
    *,
    request_digest: bytes,
    policy_refusal: RecordProblem | None,
    now: datetime,
) -> TicketCommandResult | RecordProblem | None:
    existing = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
    if isinstance(existing, RecordProblem):
        return existing
    if existing is not None:
        return _result_from_payload(existing)
    if policy_refusal is not None:
        return _refuse(transaction, actor, command, request_digest, policy_refusal, now)
    return None


def get_ticket(
    dsn: str,
    actor: Actor,
    ticket_id: UUID | str,
    project_key: str,
    *,
    telemetry: TelemetryContext,
) -> Ticket | RecordProblem:
    """Read one ticket using tenant/project predicates that reveal no foreign existence."""

    del telemetry
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        refusal = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(project_key,),
            allow_operator_read=True,
        )
        if refusal is not None:
            return refusal
        parsed_ticket_id = _resolve_ticket_reference(
            connection, actor.tenant_id, project_key, ticket_id
        )
        if parsed_ticket_id is None:
            return _scope_problem()
        row = connection.execute(
            """
            SELECT ticket.ticket_id, ticket.title, ticket.project_key,
                ticket.source_kind, ticket.source_ref,
                ticket.priority, ticket.custodian_principal_id, ticket.version,
                ticket.created_at, ticket.display_key,
                CASE WHEN confirmation.client_command_id IS NULL
                    THEN 'durability_pending' ELSE 'accepted'
                END AS durability_state
            FROM tickets AS ticket
            LEFT JOIN durability_subject_heads AS head
              ON head.tenant_id = ticket.tenant_id
             AND head.subject_kind = 'ticket'
             AND head.subject_id = ticket.ticket_id
            LEFT JOIN durability_acceptance_confirmations AS confirmation
              ON confirmation.tenant_id = head.tenant_id
             AND confirmation.principal_id = head.principal_id
             AND confirmation.client_command_id = head.client_command_id
            WHERE ticket.tenant_id = %s AND ticket.project_key = %s
              AND ticket.ticket_id = %s
            """,
            (actor.tenant_id, project_key, parsed_ticket_id),
        ).fetchone()
    return _ticket_from_row(row) if row is not None else _scope_problem()


def ticket_timeline(
    dsn: str,
    actor: Actor,
    ticket_id: UUID | str,
    project_key: str,
    *,
    telemetry: TelemetryContext,
) -> TicketTimeline | RecordProblem:
    """Read an ordered event stream using the same no-disclosure project predicate."""

    del telemetry
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        refusal = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(project_key,),
            allow_operator_read=True,
        )
        if refusal is not None:
            return refusal
        parsed_ticket_id = _resolve_ticket_reference(
            connection, actor.tenant_id, project_key, ticket_id
        )
        if parsed_ticket_id is None:
            return _scope_problem()
        rows = connection.execute(
            """
            SELECT event.event_id, event.sequence, event.kind, event.actor_principal_id,
                event.client_command_id, event.server_time, event.payload,
                ticket.project_key AS authoritative_project_key
            FROM events AS event
            JOIN tickets AS ticket
              ON ticket.tenant_id = event.tenant_id
             AND ticket.ticket_id = event.aggregate_id
            WHERE event.tenant_id = %s AND ticket.project_key = %s
              AND event.aggregate_id = %s
              AND kind IN (
                'ticket.created',
                'ticket.custody_transferred',
                'ticket.comment_added'
              )
            ORDER BY sequence
            """,
            (actor.tenant_id, project_key, parsed_ticket_id),
        ).fetchall()
    if not rows:
        return _scope_problem()
    events = tuple(_timeline_event(row) for row in rows)
    return TicketTimeline(parsed_ticket_id, events)


def _resolve_ticket_reference(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
    reference: UUID | str,
) -> UUID | None:
    if isinstance(reference, UUID):
        return reference
    row = connection.execute(
        """
        SELECT ticket_id
        FROM tickets
        WHERE tenant_id = %s AND project_key = %s AND display_key = %s
        """,
        (tenant_id, project_key, reference),
    ).fetchone()
    return cast(UUID, row["ticket_id"]) if row is not None else None


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: TicketCommand,
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


def _append_ticket_created(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    result: TicketCommandResult,
    *,
    project_key: str,
    identifiers: TicketCreationIds,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> None:
    commit = ticket_created_commit(
        actor,
        command,
        identifiers,
        project_key=project_key,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    RecordTransaction(connection).commit(
        commit.event,
        outbox_id=commit.outbox_id,
        response_body=result.response_payload(),
        status_code=201,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command.client_command_id),
            ticket_id=str(identifiers.ticket),
        ),
        now=now,
        subjects=(("ticket", identifiers.ticket),),
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
        display_key=cast(str | None, row.get("display_key")),
        durability_state=DurabilityState(str(row["durability_state"])),
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
        display_key=cast(str | None, ticket_payload.get("display_key")),
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
        payload=ticket_payload_from_mapping(
            kind,
            payload,
            legacy_project_key=str(row["authoritative_project_key"]),
        ),
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
