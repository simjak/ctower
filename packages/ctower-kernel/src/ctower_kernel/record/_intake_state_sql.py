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
from ctower_kernel.record._ticket_sql import (
    _eligible_custodian,
    _TicketIds,
)
from ctower_kernel.record.intake import (
    InboundSource,
    IntakeIntent,
    IntakeOutcome,
    IntakePromotionCommand,
    IntakeSubmitCommand,
    IntakeTaint,
)

__all__: tuple[str, ...] = ()

_ZERO_HASH = bytes(32)


def project_available(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    project_key: str,
) -> bool:
    """Recognize only the declared I1 ctower project hierarchy."""

    if project_key != "ctower":
        return False
    row = connection.execute(
        """
        SELECT 1 FROM project_delivery_checkpoint_definitions
        WHERE tenant_id = %s AND company_key = 'ctower' AND project_key = %s
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
        (f"intake-source:{actor.tenant_id}:{command.source.kind}:{command.source.ref}",),
    )
    row = connection.execute(
        """
        SELECT inbound_event_id FROM inbound_source_aliases
        WHERE tenant_id = %s AND source_kind = %s AND source_ref = %s
        """,
        (actor.tenant_id, command.source.kind, command.source.ref),
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


def prepare_action(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand | IntakePromotionCommand,
    *,
    project_key: str | None = None,
    source: InboundSource | None = None,
    ticket_ids: _TicketIds | None = None,
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
    return _prepare_create_action(
        connection,
        actor,
        command,
        source=source,
        ticket_ids=ticket_ids,
    )


def _prepare_create_action(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand | IntakePromotionCommand,
    *,
    source: InboundSource | None,
    ticket_ids: _TicketIds | None,
) -> IntakeAction | RecordProblem:
    if command.initial_custodian_id is None or command.priority is None or command.title is None:
        raise RuntimeError("Work admitted incomplete create-ticket intake")
    if not _eligible_custodian(connection, actor, command.initial_custodian_id):
        return _scope_problem(command.client_command_id)
    if ticket_ids is None:
        raise RuntimeError("create-ticket intake identifiers are unavailable")
    inbound_source = command.source if isinstance(command, IntakeSubmitCommand) else source
    if inbound_source is None:
        raise RuntimeError("promotion source provenance is unavailable")
    ticket_command = TicketCommand(
        client_command_id=command.client_command_id,
        initial_custodian_id=command.initial_custodian_id,
        priority=command.priority,
        source=SourceReference(inbound_source.kind, inbound_source.ref),
        title=command.title,
    )
    return IntakeAction(
        IntakeOutcome.TICKET_CREATED,
        ticket_ids.ticket,
        1,
        ticket_command,
        ticket_ids,
    )


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
        SELECT ticket.version, project.project_key
        FROM tickets AS ticket
        JOIN ticket_project_bindings AS project
          ON project.ticket_id = ticket.ticket_id AND project.tenant_id = ticket.tenant_id
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
