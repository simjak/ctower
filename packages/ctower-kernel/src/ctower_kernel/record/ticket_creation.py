"""Record-owned primitives for composing ticket creation into one transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    TicketCreatedPayload,
)
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.interface import (
    Actor,
    PrincipalKind,
    RecordProblem,
    TicketCommand,
)
from ctower_kernel.record.transaction import EventCommit
from ctower_kernel.telemetry import TelemetryContext

__all__ = [
    "TicketCreationIds",
    "allocate_ticket_display_key",
    "initial_custody_problem",
    "initial_custody_project",
    "insert_ticket_state",
    "new_ticket_creation_ids",
    "ticket_created_commit",
]

_ZERO_HASH = bytes(32)


@dataclass(frozen=True, slots=True)
class TicketCreationIds:
    """Identifiers allocated together for one new ticket append."""

    ticket: UUID
    event: UUID
    outbox: UUID


def new_ticket_creation_ids(now: datetime) -> TicketCreationIds:
    """Allocate the ticket, canonical event, and outbox identities."""

    return TicketCreationIds(*(uuid7(now) for _ in range(3)))


def initial_custody_project(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    custodian_id: UUID,
) -> str | RecordProblem:
    """Resolve the project while enforcing the one initial-custody policy."""

    row = connection.execute(
        """
        SELECT principal.kind, seat.project_key
        FROM principals AS principal
        LEFT JOIN project_seats AS seat
          ON seat.principal_id = principal.principal_id
         AND seat.tenant_id = principal.tenant_id
        WHERE principal.tenant_id = %s AND principal.principal_id = %s
          AND NOT principal.disabled
        """,
        (actor.tenant_id, custodian_id),
    ).fetchone()
    if row is None:
        return _scope_problem(command_id)
    authorized = str(row["kind"]) == PrincipalKind.COMMANDER.value and (
        actor.kind is PrincipalKind.OPERATOR
        or (actor.kind is PrincipalKind.COMMANDER and custodian_id == actor.principal_id)
    )
    if not authorized:
        return RecordProblem(
            code="unauthorized",
            detail=(
                "Initial custody requires Commander self-custody or an operator placing "
                "custody with an eligible Commander."
            ),
            status=403,
            title="Initial custody refused",
            command_id=command_id,
        )
    if row["project_key"] is None:
        return RecordProblem(
            code="project-grant-required",
            detail="Initial custody requires a Commander with one explicit project grant.",
            status=403,
            title="Project grant required",
            command_id=command_id,
        )
    return str(row["project_key"])


def initial_custody_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    custodian_id: UUID,
) -> RecordProblem | None:
    """Return only the refusal for callers that already own project resolution."""

    project = initial_custody_project(connection, actor, command_id, custodian_id)
    return project if isinstance(project, RecordProblem) else None


def insert_ticket_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    *,
    project_key: str,
    identifiers: TicketCreationIds,
    now: datetime,
) -> str | None:
    """Persist the ticket and its initial lifecycle, custody, and priority facts."""

    display_key = allocate_ticket_display_key(connection, actor.tenant_id, project_key)

    connection.execute(
        """
        INSERT INTO tickets (
            ticket_id, tenant_id, title, source_kind, source_ref, priority,
            custodian_principal_id, version, durability_state, created_by, created_at,
            project_key, display_key
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 'durability_pending', %s, %s, %s, %s)
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
            project_key,
            display_key,
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
    return display_key


def allocate_ticket_display_key(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    project_key: str,
) -> str | None:
    """Read the active authored prefix and reserve one project-local number atomically."""

    prefix_rows = connection.execute(
        """
        SELECT revision.project_prefix
        FROM company_bundle_active AS active
        JOIN company_bundle_members AS member
          ON member.tenant_id = active.tenant_id
         AND member.bundle_revision_id = active.bundle_revision_id
        JOIN catalog_component_revisions AS revision
          ON revision.tenant_id = member.tenant_id
         AND revision.component_revision_id = member.component_revision_id
        JOIN catalog_components AS component
          ON component.tenant_id = revision.tenant_id
         AND component.component_id = revision.component_id
        WHERE active.tenant_id = %s
          AND component.kind = 'project'
          AND split_part(component.component_key, '.', 1) = %s
          AND revision.project_prefix IS NOT NULL
        """,
        (tenant_id, project_key),
    ).fetchall()
    if not prefix_rows:
        return None
    prefixes = {str(row["project_prefix"]) for row in prefix_rows}
    if len(prefixes) != 1:
        raise RuntimeError("active project prefix is ambiguous")
    prefix = next(iter(prefixes))
    sequence = connection.execute(
        """
        INSERT INTO ticket_display_sequences (tenant_id, project_key, next_number)
        VALUES (%s, %s, 2)
        ON CONFLICT (tenant_id, project_key) DO UPDATE
        SET next_number = ticket_display_sequences.next_number + 1
        RETURNING next_number - 1 AS allocated_number
        """,
        (tenant_id, project_key),
    ).fetchone()
    if sequence is None:
        raise RuntimeError("ticket display sequence did not allocate a number")
    return f"{prefix}-{int(cast(int, sequence['allocated_number']))}"


def ticket_created_commit(
    actor: Actor,
    command: TicketCommand,
    identifiers: TicketCreationIds,
    *,
    project_key: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventCommit:
    """Build the canonical ticket-created append for a caller-owned transaction."""

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
            project_key=project_key,
            source_kind=command.source.kind,
            source_ref=command.source.ref,
            title=command.title,
        ),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"ticket:{identifiers.ticket}",
        tenant_id=actor.tenant_id,
    )
    return EventCommit(event, identifiers.outbox)


def _insert_initial_custody(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: TicketCommand,
    *,
    identifiers: TicketCreationIds,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO assignment_intervals (
            ticket_id, tenant_id, interval_sequence, assignment_kind, principal_id,
            assigned_at, released_at, changed_by, reason, client_command_id, episode_number
        ) VALUES (%s, %s, 1, 'ticket_custodian', %s, %s, NULL, %s,
            'initial eligible custodian', %s, 1)
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
    identifiers: TicketCreationIds,
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


def _scope_problem(command_id: UUID) -> RecordProblem:
    return RecordProblem(
        code="tenant-scope-denied",
        detail="The requested ticket is unavailable in the authenticated tenant scope.",
        status=404,
        title="Ticket unavailable",
        command_id=command_id,
    )
