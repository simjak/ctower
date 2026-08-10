"""Thread, alias, and ticket-action state preparation for Record intake."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import (
    Actor,
    RecordProblem,
    SourceReference,
    TicketCommand,
)
from ctower_kernel.record._intake_command_sql import IntakeAction, IntakeThreadState
from ctower_kernel.record._intake_command_sql import scope_problem as _scope_problem
from ctower_kernel.record._intake_command_sql import version_problem as _version_problem
from ctower_kernel.record.intake import (
    InboundSource,
    IntakeIntent,
    IntakeOutcome,
    IntakePromotionCommand,
    IntakeSubmitCommand,
    IntakeTaint,
)
from ctower_kernel.record.ticket_creation import (
    TicketCreationIds,
)
from ctower_kernel.record.ticket_creation import (
    initial_custody_problem as _initial_custody_problem,
)

__all__: tuple[str, ...] = ()

_ZERO_HASH = bytes(32)


def project_available(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    project_key: str,
) -> bool:
    """Recognize any project declared by the active tenant hierarchy."""

    row = connection.execute(
        """
        SELECT 1 FROM project_delivery_checkpoint_definitions
        WHERE tenant_id = %s AND project_key = %s
        LIMIT 1
        """,
        (actor.tenant_id, project_key),
    ).fetchone()
    return row is not None


def lock_thread(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand,
    thread_id: UUID,
) -> IntakeThreadState | RecordProblem:
    if command.thread_id is None:
        return IntakeThreadState(thread_id, 1, 1, _ZERO_HASH, is_new=True)
    row = connection.execute(
        """
        SELECT thread.version, thread.project_key,
            (
                SELECT event_hash FROM events
                WHERE tenant_id = thread.tenant_id
                  AND stream_id = 'inbound-thread:' || thread.thread_id::text
                ORDER BY sequence DESC LIMIT 1
            ) AS previous_hash
        FROM inbound_threads AS thread
        WHERE thread.tenant_id = %s AND thread.thread_id = %s
        FOR UPDATE
        """,
        (actor.tenant_id, thread_id),
    ).fetchone()
    if row is None or str(row["project_key"]) != command.project_key:
        return _scope_problem(command.client_command_id)
    current = int(cast(int, row["version"]))
    if current != command.expected_thread_version:
        return _version_problem(command.client_command_id, current)
    previous = row["previous_hash"]
    if previous is None:
        raise RuntimeError("existing inbound thread has no canonical event")
    position = connection.execute(
        """
        SELECT COALESCE(max(position), 0) + 1 AS next_position
        FROM inbound_events WHERE tenant_id = %s AND thread_id = %s
        """,
        (actor.tenant_id, thread_id),
    ).fetchone()
    if position is None:
        raise RuntimeError("inbound event position query returned no row")
    return IntakeThreadState(
        thread_id,
        current + 1,
        int(cast(int, position["next_position"])),
        bytes(cast(bytes, previous)),
        is_new=False,
    )


def insert_new_thread(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand,
    state: IntakeThreadState,
    *,
    now: datetime,
) -> None:
    if not state.is_new:
        return
    connection.execute(
        """
        INSERT INTO inbound_threads (
            thread_id, tenant_id, project_key, version, created_by, created_at
        ) VALUES (%s, %s, %s, 1, %s, %s)
        """,
        (state.thread_id, actor.tenant_id, command.project_key, actor.principal_id, now),
    )


def reserve_source_alias(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand,
    thread_id: UUID,
) -> RecordProblem | None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (
            "intake-source:"
            f"{actor.tenant_id}:{command.project_key}:"
            f"{command.source.kind}:{command.source.ref}",
        ),
    )
    row = connection.execute(
        """
        SELECT inbound_event_id FROM inbound_source_aliases
        WHERE tenant_id = %s AND project_key = %s
          AND source_kind = %s AND source_ref = %s
        """,
        (actor.tenant_id, command.project_key, command.source.kind, command.source.ref),
    ).fetchone()
    if row is None:
        return None
    return RecordProblem(
        code="intake-source-conflict",
        detail="The inbound source alias already identifies another immutable event.",
        status=409,
        title="Inbound source alias conflict",
        command_id=command.client_command_id,
        unmet_facts=(f"inbound_event:{row['inbound_event_id']}", f"thread:{thread_id}"),
    )


def initial_custody_problem(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand | IntakePromotionCommand,
) -> RecordProblem | None:
    """Establish target authority before consulting observable intake state."""

    if (
        command.intent is not IntakeIntent.CREATE_TICKET
        or command.initial_custodian_id is None
        or (
            isinstance(command, IntakeSubmitCommand)
            and command.taint is IntakeTaint.QUARANTINE_REQUIRED
        )
    ):
        return None
    return _initial_custody_problem(
        connection,
        actor,
        command.client_command_id,
        command.initial_custodian_id,
    )


def prepare_action(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand | IntakePromotionCommand,
    *,
    project_key: str | None = None,
    source: InboundSource | None = None,
    ticket_ids: TicketCreationIds | None = None,
    request_ids: tuple[UUID, UUID] | None = None,
    now: datetime | None = None,
) -> IntakeAction | RecordProblem:
    if (
        isinstance(command, IntakeSubmitCommand)
        and command.taint is IntakeTaint.QUARANTINE_REQUIRED
    ):
        return IntakeAction(IntakeOutcome.QUARANTINED, None, None, None, None)
    if command.intent is IntakeIntent.DISCUSSION:
        return IntakeAction(IntakeOutcome.DISCUSSION, None, None, None, None)
    if command.intent is IntakeIntent.LINK_TICKET:
        return _prepare_link_action(connection, actor, command, project_key=project_key)
    if command.intent is IntakeIntent.CREATE_REQUEST:
        return _prepare_request_action(
            connection,
            actor,
            command,
            project_key=project_key,
            request_ids=request_ids,
            now=now,
        )
    return _prepare_create_action(
        connection,
        actor,
        command,
        project_key=project_key,
        source=source,
        ticket_ids=ticket_ids,
    )


def _prepare_create_action(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand | IntakePromotionCommand,
    *,
    project_key: str | None,
    source: InboundSource | None,
    ticket_ids: TicketCreationIds | None,
) -> IntakeAction | RecordProblem:
    if command.initial_custodian_id is None or command.priority is None or command.title is None:
        raise RuntimeError("Work admitted incomplete create-ticket intake")
    source_reference = _ticket_source(command, source)
    resolved_project = (
        command.project_key if isinstance(command, IntakeSubmitCommand) else project_key
    )
    if resolved_project is None:
        raise RuntimeError("create-ticket intake project scope is unavailable")
    custody_problem = initial_custody_problem(connection, actor, command)
    if custody_problem is not None:
        return custody_problem
    if ticket_ids is None:
        raise RuntimeError("create-ticket intake identifiers are unavailable")
    ticket_command = TicketCommand(
        client_command_id=command.client_command_id,
        initial_custodian_id=command.initial_custodian_id,
        priority=command.priority,
        project_key=resolved_project,
        source=source_reference,
        title=command.title,
    )
    return IntakeAction(
        IntakeOutcome.TICKET_CREATED,
        ticket_ids.ticket,
        1,
        ticket_command,
        ticket_ids,
    )


def _prepare_request_action(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand | IntakePromotionCommand,
    *,
    project_key: str | None,
    request_ids: tuple[UUID, UUID] | None,
    now: datetime | None,
) -> IntakeAction | RecordProblem:
    resolved_project = (
        command.project_key if isinstance(command, IntakeSubmitCommand) else project_key
    )
    if resolved_project is None or request_ids is None or now is None:
        raise RuntimeError("create-request intake identifiers are unavailable")
    epoch = _request_epoch_refusal(connection, actor, command.client_command_id)
    if epoch is not None:
        return epoch
    number = _allocate_request_number(connection, actor.tenant_id, now)
    owner = _request_owner(connection, actor, resolved_project)
    return IntakeAction(
        IntakeOutcome.REQUEST_CREATED,
        None,
        None,
        None,
        None,
        request_ids[0],
        number,
        owner,
        request_ids[1],
    )


def _allocate_request_number(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, now: datetime
) -> int:
    row = connection.execute(
        """
        INSERT INTO request_number_allocators (tenant_id, last_number, advanced_at)
        VALUES (%s, 1, %s)
        ON CONFLICT (tenant_id) DO UPDATE
        SET last_number = request_number_allocators.last_number + 1,
            advanced_at = EXCLUDED.advanced_at
        RETURNING last_number
        """,
        (tenant_id, now),
    ).fetchone()
    if row is None:
        raise RuntimeError("Request allocator returned no number")
    return int(cast(int, row["last_number"]))


def _request_owner(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, project_key: str
) -> UUID:
    row = connection.execute(
        """
        SELECT principal_id FROM project_seats
        WHERE tenant_id = %s AND project_key = %s AND principal_id = %s
        UNION ALL
        SELECT binding.principal_id FROM human_role_bindings AS binding
        LEFT JOIN human_role_binding_revocations AS revocation
          ON revocation.tenant_id = binding.tenant_id
         AND revocation.binding_id = binding.binding_id
        WHERE binding.tenant_id = %s AND binding.principal_id = %s
          AND %s = ANY(binding.project_keys) AND revocation.binding_id IS NULL
        LIMIT 1
        """,
        (
            actor.tenant_id,
            project_key,
            actor.principal_id,
            actor.tenant_id,
            actor.principal_id,
            project_key,
        ),
    ).fetchone()
    if row is not None:
        return cast(UUID, row["principal_id"])
    commander = connection.execute(
        """
        SELECT principal.principal_id
        FROM project_seats AS seat
        JOIN principals AS principal
          ON principal.tenant_id = seat.tenant_id
         AND principal.principal_id = seat.principal_id
        WHERE seat.tenant_id = %s AND seat.project_key = %s
          AND principal.kind = 'commander' AND NOT principal.disabled
        ORDER BY principal.created_at, principal.principal_id LIMIT 1
        """,
        (actor.tenant_id, project_key),
    ).fetchone()
    if commander is None:
        raise RuntimeError("Request project has no active Commander")
    return cast(UUID, commander["principal_id"])


def _request_epoch_refusal(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, command_id: UUID
) -> RecordProblem | None:
    row = connection.execute(
        """
        SELECT fact.state, confirmation.acceptance_position
        FROM request_cutover_epoch_facts AS fact
        LEFT JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = fact.tenant_id
         AND confirmation.principal_id = fact.recorded_by
         AND confirmation.client_command_id = fact.command_id
        WHERE fact.tenant_id = %s ORDER BY fact.sequence DESC LIMIT 1
        """,
        (actor.tenant_id,),
    ).fetchone()
    if row is None or (row["state"] == "completed" and row["acceptance_position"] is not None):
        return None
    return RecordProblem(
        code="migration-import-finalization-refused",
        detail="Request intake is fenced until the authority epoch is completed and accepted.",
        status=409,
        title="Request authority epoch unavailable",
        command_id=command_id,
    )


def _ticket_source(
    command: IntakeSubmitCommand | IntakePromotionCommand,
    promotion_source: InboundSource | None,
) -> SourceReference:
    inbound_source = (
        command.source if isinstance(command, IntakeSubmitCommand) else promotion_source
    )
    if inbound_source is None:
        raise RuntimeError("promotion source provenance is unavailable")
    return SourceReference(inbound_source.kind, inbound_source.ref)


def _prepare_link_action(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand | IntakePromotionCommand,
    *,
    project_key: str | None,
) -> IntakeAction | RecordProblem:
    if command.target_ticket_id is None or command.expected_ticket_version is None:
        raise RuntimeError("Work admitted incomplete link-ticket intake")
    row = connection.execute(
        """
        SELECT ticket.version, ticket.project_key
        FROM tickets AS ticket
        WHERE ticket.tenant_id = %s AND ticket.ticket_id = %s
        FOR UPDATE OF ticket
        """,
        (actor.tenant_id, command.target_ticket_id),
    ).fetchone()
    expected_project = (
        command.project_key if isinstance(command, IntakeSubmitCommand) else project_key
    )
    if expected_project is None:
        raise RuntimeError("promotion project scope is unavailable")
    if row is None or str(row["project_key"]) != expected_project:
        return _scope_problem(command.client_command_id)
    version = int(cast(int, row["version"]))
    if version != command.expected_ticket_version:
        return _version_problem(command.client_command_id, version)
    return IntakeAction(
        IntakeOutcome.TICKET_LINKED,
        command.target_ticket_id,
        version,
        None,
        None,
    )
