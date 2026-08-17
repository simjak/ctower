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
from ctower_kernel.record.events import (
    EventKind,
    WorkflowChangedPayload,
    ticket_payload_from_mapping,
)
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
from ctower_kernel.record.workflow_validation import workflow_payload_for_read
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
        insert_ticket_state(
            connection,
            actor,
            command,
            project_key=project,
            identifiers=identifiers,
            now=now,
        )
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
    ticket_id: UUID,
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
        row = connection.execute(
            """
            SELECT ticket.ticket_id, ticket.title, ticket.project_key,
                ticket.source_kind, ticket.source_ref,
                ticket.priority, ticket.custodian_principal_id, ticket.version,
                ticket.created_at,
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
            (actor.tenant_id, project_key, ticket_id),
        ).fetchone()
    return _ticket_from_row(row) if row is not None else _scope_problem()


def ticket_timeline(
    dsn: str,
    actor: Actor,
    ticket_id: UUID,
    project_key: str,
    *,
    telemetry: TelemetryContext,
) -> TicketTimeline | RecordProblem:
    """Read an ordered ticket-linked event stream using the same project predicate."""

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
        rows = connection.execute(
            """
            SELECT event.event_id, event.sequence, event.kind, event.actor_principal_id,
                event.client_command_id, event.server_time, event.payload,
                ticket.project_key AS authoritative_project_key
            FROM event_links AS link
            JOIN events AS event
              ON event.event_id = link.event_id AND event.tenant_id = link.tenant_id
            JOIN tickets AS ticket
              ON ticket.tenant_id = link.tenant_id AND ticket.ticket_id = link.subject_id
            WHERE link.tenant_id = %s AND link.subject_kind = 'ticket'
              AND ticket.project_key = %s AND link.subject_id = %s
              AND event.kind IN (
                'ticket.created',
                'ticket.custody_transferred',
                'ticket.comment_added',
                'workflow.changed'
              )
            ORDER BY event.record_position
            """,
            (actor.tenant_id, project_key, ticket_id),
        ).fetchall()
    if not rows:
        return _scope_problem()
    events = tuple(_timeline_event(row) for row in rows)
    return TicketTimeline(ticket_id, events)


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
            kind, payload, legacy_project_key=str(row["authoritative_project_key"])
        )
        if kind is not EventKind.WORKFLOW_CHANGED
        else _workflow_payload_from_mapping(payload),
        sequence=int(cast(int, row["sequence"])),
    )


def _workflow_payload_from_mapping(payload: dict[str, object]) -> WorkflowChangedPayload:
    normalized = workflow_payload_for_read(payload)
    expected = {
        "evaluation_ref",
        "lifecycle_facts",
        "operation",
        "source_stage",
        "stage",
        "ticket_id",
        "workflow_ref",
        "workflow_version",
    }
    if set(normalized) != expected:
        raise ValueError("event payload fields do not match the authored variant")
    lifecycle_facts = normalized["lifecycle_facts"]
    if not isinstance(lifecycle_facts, list) or any(
        not isinstance(item, str) for item in lifecycle_facts
    ):
        raise TypeError("lifecycle_facts must be a list of strings")
    workflow_version = normalized["workflow_version"]
    if type(workflow_version) is not int:
        raise TypeError("workflow_version must be an integer")
    strings = _workflow_payload_strings(normalized)
    return WorkflowChangedPayload(
        operation=strings["operation"],
        ticket_id=UUID(strings["ticket_id"]),
        workflow_ref=strings["workflow_ref"],
        workflow_version=workflow_version,
        stage=strings["stage"],
        lifecycle_facts=tuple(lifecycle_facts),
        source_stage=strings["source_stage"],
        evaluation_ref=strings["evaluation_ref"],
    )


def _workflow_payload_strings(payload: dict[str, object]) -> dict[str, str]:
    names = ("evaluation_ref", "operation", "source_stage", "stage", "ticket_id", "workflow_ref")
    values = {name: payload[name] for name in names}
    if not all(isinstance(value, str) for value in values.values()):
        raise TypeError("workflow payload string fields must be strings")
    return {name: cast(str, value) for name, value in values.items()}


def _scope_problem(command_id: UUID | None = None) -> RecordProblem:
    return RecordProblem(
        code="tenant-scope-denied",
        detail="The requested ticket is unavailable in the authenticated tenant scope.",
        status=404,
        title="Ticket unavailable",
        command_id=command_id,
    )
