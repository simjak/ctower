"""Canonical event and outbox construction for atomic Record intake."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import cast
from uuid import UUID

from ctower_kernel.record import Actor
from ctower_kernel.record._intake_command_sql import IntakeAction, IntakeThreadState
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    InboundEventPromotedPayload,
    InboundEventRecordedPayload,
)
from ctower_kernel.record.intake import (
    IntakeCommandResult,
    IntakePromotionCommand,
    IntakeSubmitCommand,
)
from ctower_kernel.record.ticket_creation import ticket_created_commit
from ctower_kernel.record.transaction import EventCommit
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def submit_commits(
    actor: Actor,
    command: IntakeSubmitCommand,
    state: IntakeThreadState,
    result: IntakeCommandResult,
    action: IntakeAction,
    event_id: UUID,
    outbox_id: UUID,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[EventCommit, ...]:
    intake_event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=state.thread_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.INBOUND_EVENT_RECORDED,
        origin=EventOrigin.API,
        payload=InboundEventRecordedPayload(
            inbound_event_id=event_id,
            source_kind=command.source.kind,
            source_ref=command.source.ref,
            project_key=command.project_key,
            position=state.next_position,
            intent=command.intent.value,
            taint=command.taint.value,
            outcome=result.outcome.value,
            content_digest=f"sha256:{hashlib.sha256(command.content.encode()).hexdigest()}",
            ticket_id=result.ticket_id,
        ),
        prev_hash=state.previous_hash,
        request_sha256=request_digest,
        sequence=state.version,
        server_time=now,
        stream_id=f"inbound-thread:{state.thread_id}",
        tenant_id=actor.tenant_id,
    )
    commits = [EventCommit(intake_event, outbox_id)]
    ticket = _ticket_commit(
        actor,
        action,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    if ticket is not None:
        commits.append(ticket)
    return tuple(commits)


def promotion_commits(
    actor: Actor,
    command: IntakePromotionCommand,
    inbound: dict[str, object],
    result: IntakeCommandResult,
    action: IntakeAction,
    event_id: UUID,
    outbox_id: UUID,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[EventCommit, ...]:
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=result.thread_id,
        causation_id=result.inbound_event_id,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.INBOUND_EVENT_PROMOTED,
        origin=EventOrigin.API,
        payload=InboundEventPromotedPayload(
            inbound_event_id=result.inbound_event_id,
            source_kind=result.source.kind,
            source_ref=result.source.ref,
            project_key=result.project_key,
            intent=command.intent.value,
            outcome=result.outcome.value,
            ticket_id=cast(UUID, result.ticket_id),
        ),
        prev_hash=bytes(cast(bytes, inbound["event_hash"])),
        request_sha256=request_digest,
        sequence=result.thread_version,
        server_time=now,
        stream_id=f"inbound-thread:{result.thread_id}",
        tenant_id=actor.tenant_id,
    )
    commits = [EventCommit(event, outbox_id)]
    ticket = _ticket_commit(
        actor,
        action,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    if ticket is not None:
        commits.append(ticket)
    return tuple(commits)


def _ticket_commit(
    actor: Actor,
    action: IntakeAction,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventCommit | None:
    if action.ticket_command is None or action.ticket_ids is None:
        return None
    command = action.ticket_command
    if command.project_key is None:
        raise RuntimeError("create-ticket intake project scope is unavailable")
    return ticket_created_commit(
        actor,
        command,
        action.ticket_ids,
        project_key=command.project_key,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
