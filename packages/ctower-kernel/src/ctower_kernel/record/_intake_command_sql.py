"""Shared command, replay, CAS, and identity mechanics for Record intake."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import (
    Actor,
    RecordProblem,
    TicketCommand,
)
from ctower_kernel.record.intake import (
    InboundSource,
    IntakeCommandResult,
    IntakeOutcome,
    IntakePromotionCommand,
)
from ctower_kernel.record.ticket_creation import TicketCreationIds
from ctower_kernel.record.transaction import RecordTransaction

__all__: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntakeThreadState:
    thread_id: UUID
    version: int
    next_position: int
    previous_hash: bytes
    is_new: bool


@dataclass(frozen=True, slots=True)
class IntakeAction:
    outcome: IntakeOutcome
    ticket_id: UUID | None
    ticket_version: int | None
    ticket_command: TicketCommand | None
    ticket_ids: TicketCreationIds | None
    request_id: UUID | None = None
    request_number: int | None = None
    request_owner_id: UUID | None = None
    request_event_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class _SubmitIds:
    thread: UUID
    inbound_event: UUID
    ticket: TicketCreationIds | None
    ticket_subject: UUID | None
    request: UUID | None
    request_event: UUID | None


def resolve_inbound_for_promotion(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakePromotionCommand,
) -> UUID | RecordProblem:
    """Resolve the durability subject without taking an aggregate lock."""

    row = connection.execute(
        """
        SELECT thread_id FROM inbound_events
        WHERE tenant_id = %s AND inbound_event_id = %s
        """,
        (actor.tenant_id, command.inbound_event_id),
    ).fetchone()
    if row is None:
        return scope_problem(command.client_command_id)
    return cast(UUID, row["thread_id"])


def lock_inbound_for_promotion(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: IntakePromotionCommand,
) -> dict[str, object] | RecordProblem:
    row = connection.execute(
        """
        SELECT inbound.thread_id, inbound.source_kind, inbound.source_ref, inbound.content,
            inbound.initial_outcome, inbound.taint,
            thread.project_key, thread.version,
            (
                SELECT event_hash FROM events
                WHERE tenant_id = thread.tenant_id
                  AND stream_id = 'inbound-thread:' || thread.thread_id::text
                ORDER BY sequence DESC LIMIT 1
            ) AS event_hash,
            link.ticket_id AS linked_ticket_id,
            request.request_id AS linked_request_id,
            EXISTS (
                SELECT 1 FROM inbound_quarantines AS quarantine
                WHERE quarantine.tenant_id = inbound.tenant_id
                  AND quarantine.inbound_event_id = inbound.inbound_event_id
            ) AS governed_by_quarantine
        FROM inbound_events AS inbound
        JOIN inbound_threads AS thread
          ON thread.thread_id = inbound.thread_id AND thread.tenant_id = inbound.tenant_id
        LEFT JOIN inbound_ticket_links AS link
          ON link.inbound_event_id = inbound.inbound_event_id
         AND link.tenant_id = inbound.tenant_id
        LEFT JOIN requests AS request
          ON request.inbound_event_id = inbound.inbound_event_id
         AND request.tenant_id = inbound.tenant_id
        WHERE inbound.tenant_id = %s AND inbound.inbound_event_id = %s
        FOR UPDATE OF thread
        """,
        (actor.tenant_id, command.inbound_event_id),
    ).fetchone()
    if row is None:
        return scope_problem(command.client_command_id)
    if (
        str(row["initial_outcome"]) != IntakeOutcome.DISCUSSION.value
        or str(row["taint"]) != "authenticated"
        or bool(row["governed_by_quarantine"])
    ):
        return RecordProblem(
            code="intake-promotion-ineligible",
            detail="Only an authenticated, ungoverned discussion event may be promoted.",
            status=409,
            title="Inbound event is not promotable",
            command_id=command.client_command_id,
        )
    if row["linked_ticket_id"] is not None or row["linked_request_id"] is not None:
        target = row["linked_ticket_id"] or row["linked_request_id"]
        return RecordProblem(
            code="intake-already-promoted",
            detail="The inbound event already has its one durable authority edge.",
            status=409,
            title="Inbound event already promoted",
            command_id=command.client_command_id,
            unmet_facts=(f"authority:{target}",),
        )
    current = int(cast(int, row["version"]))
    if current != command.expected_thread_version:
        return version_problem(command.client_command_id, current)
    return row


def advance_thread(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    thread_id: UUID,
    expected_version: int,
) -> None:
    row = connection.execute(
        """
        UPDATE inbound_threads SET version = version + 1
        WHERE tenant_id = %s AND thread_id = %s AND version = %s
        RETURNING version
        """,
        (tenant_id, thread_id, expected_version),
    ).fetchone()
    if row is None:
        raise RuntimeError("locked inbound thread version changed unexpectedly")


def subjects(
    thread_id: UUID,
    inbound_event_id: UUID,
    ticket_id: UUID | None,
    request_id: UUID | None = None,
) -> tuple[tuple[str, UUID], ...]:
    values = [("inbound_thread", thread_id), ("inbound_event", inbound_event_id)]
    if ticket_id is not None:
        values.append(("ticket", ticket_id))
    if request_id is not None:
        values.append(("request", request_id))
    return tuple(values)


def event_ids(event_id: UUID, action: IntakeAction) -> tuple[UUID, ...]:
    if action.request_event_id is not None:
        return (event_id, action.request_event_id)
    if action.ticket_ids is None:
        return (event_id,)
    return (event_id, action.ticket_ids.event)


def refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def result_from_payload(payload: dict[str, object]) -> IntakeCommandResult:
    source = cast(dict[str, object], payload["source"])
    ticket_id = payload.get("ticket_id")
    ticket_version = payload.get("ticket_version")
    reason = payload.get("quarantine_reason")
    request_id = payload.get("request_id")
    request_number = payload.get("request_number")
    return IntakeCommandResult(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        inbound_event_id=UUID(str(payload["inbound_event_id"])),
        outcome=IntakeOutcome(str(payload["outcome"])),
        project_key=str(payload["project_key"]),
        source=InboundSource(str(source["kind"]), str(source["ref"])),
        thread_id=UUID(str(payload["thread_id"])),
        thread_version=int(cast(int, payload["thread_version"])),
        ticket_id=UUID(str(ticket_id)) if ticket_id is not None else None,
        ticket_version=int(cast(int, ticket_version)) if ticket_version is not None else None,
        quarantine_reason=str(reason) if reason is not None else None,
        request_id=UUID(str(request_id)) if request_id is not None else None,
        request_number=int(cast(int, request_number)) if request_number is not None else None,
    )


def scope_problem(command_id: UUID) -> RecordProblem:
    return RecordProblem(
        code="tenant-scope-denied",
        detail="The requested intake subject is unavailable in the authenticated scope.",
        status=404,
        title="Intake subject unavailable",
        command_id=command_id,
    )


def version_problem(command_id: UUID, current: int) -> RecordProblem:
    return RecordProblem(
        code="version-conflict",
        detail="The intake aggregate version does not match the expected version.",
        status=409,
        title="Intake version conflict",
        command_id=command_id,
        current_version=current,
    )


def uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
