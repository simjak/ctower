"""Authoritative intake row application inside one Record transaction."""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor
from ctower_kernel.record._intake_command_sql import IntakeAction, IntakeThreadState
from ctower_kernel.record._intake_request_sql import insert_request_state
from ctower_kernel.record.intake import (
    IntakeCommandResult,
    IntakeOutcome,
    IntakeSubmitCommand,
)
from ctower_kernel.record.ticket_creation import insert_ticket_state

__all__ = ["apply_action_state", "insert_inbound_event"]


def insert_inbound_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakeSubmitCommand,
    state: IntakeThreadState,
    result: IntakeCommandResult,
    *,
    now: datetime,
) -> None:
    """Persist the immutable inbound event, alias, and optional quarantine fact."""

    connection.execute(
        """
        INSERT INTO inbound_events (
            inbound_event_id, tenant_id, thread_id, position, source_kind, source_ref,
            content, content_digest, taint, initial_intent, initial_outcome,
            recorded_by, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.inbound_event_id,
            actor.tenant_id,
            state.thread_id,
            state.next_position,
            command.source.kind,
            command.source.ref,
            command.content,
            hashlib.sha256(command.content.encode()).digest(),
            command.taint.value,
            command.intent.value,
            result.outcome.value,
            actor.principal_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO inbound_source_aliases (
            tenant_id, source_kind, source_ref, inbound_event_id, thread_id,
            project_key, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            command.source.kind,
            command.source.ref,
            result.inbound_event_id,
            state.thread_id,
            command.project_key,
            now,
        ),
    )
    if result.outcome is IntakeOutcome.QUARANTINED:
        _insert_quarantine(connection, actor, result, now=now)


def _insert_quarantine(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    result: IntakeCommandResult,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO inbound_quarantines (
            inbound_event_id, tenant_id, reason, recorded_by, recorded_at
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (
            result.inbound_event_id,
            actor.tenant_id,
            result.quarantine_reason,
            actor.principal_id,
            now,
        ),
    )


def apply_action_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    action: IntakeAction,
    result: IntakeCommandResult,
    *,
    content: str,
    promoted: bool,
    now: datetime,
) -> None:
    """Apply the Request/Ticket result that was already authorized and allocated."""

    if action.request_id is not None:
        insert_request_state(
            connection,
            actor,
            command_id,
            action,
            result,
            content=content,
            now=now,
        )
    if action.ticket_command is not None and action.ticket_ids is not None:
        _insert_ticket(connection, actor, action, result, now=now)
    if action.ticket_id is not None:
        _insert_ticket_link(
            connection,
            actor,
            command_id,
            action,
            result,
            promoted=promoted,
            now=now,
        )


def _insert_ticket(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    action: IntakeAction,
    result: IntakeCommandResult,
    *,
    now: datetime,
) -> None:
    if action.ticket_command is None or action.ticket_ids is None:
        raise RuntimeError("create-ticket intake action is incomplete")
    insert_ticket_state(
        connection,
        actor,
        action.ticket_command,
        project_key=result.project_key,
        identifiers=action.ticket_ids,
        now=now,
    )
    connection.execute(
        """
        INSERT INTO ticket_project_bindings (
            ticket_id, tenant_id, project_key, run_id, source_namespace,
            immutable_source_id, bound_at, inbound_event_id
        ) VALUES (%s, %s, %s, NULL, NULL, NULL, %s, %s)
        """,
        (
            action.ticket_ids.ticket,
            actor.tenant_id,
            result.project_key,
            now,
            result.inbound_event_id,
        ),
    )


def _insert_ticket_link(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command_id: UUID,
    action: IntakeAction,
    result: IntakeCommandResult,
    *,
    promoted: bool,
    now: datetime,
) -> None:
    link_kind = (
        "promotion_create"
        if promoted and action.outcome is IntakeOutcome.TICKET_CREATED
        else "promotion_link"
        if promoted
        else "initial_create"
        if action.outcome is IntakeOutcome.TICKET_CREATED
        else "initial_link"
    )
    connection.execute(
        """
        INSERT INTO inbound_ticket_links (
            inbound_event_id, tenant_id, thread_id, ticket_id, link_kind,
            command_id, linked_by, linked_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            result.inbound_event_id,
            actor.tenant_id,
            result.thread_id,
            action.ticket_id,
            link_kind,
            command_id,
            actor.principal_id,
            now,
        ),
    )
