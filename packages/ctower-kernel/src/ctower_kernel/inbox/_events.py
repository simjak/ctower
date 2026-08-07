"""Typed native-inbox event construction."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.inbox.models import InboxPromotionCommand, InboxSendCommand
from ctower_kernel.record import Actor
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.inbox_events import (
    InboxMessageAppendedPayload,
    InboxParticipant,
    InboxThreadOpenedPayload,
    InboxThreadPromotedToTicketPayload,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()

_ZERO_HASH = bytes(32)


def _promotion_event(
    actor: Actor,
    command: InboxPromotionCommand,
    last_hash: bytes,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[EventEnvelope, UUID]:
    event_id, outbox_id = uuid7(now), uuid7(now)
    return (
        EventEnvelope(
            actor_principal_id=actor.principal_id,
            aggregate_id=command.thread_id,
            causation_id=None,
            client_command_id=command.client_command_id,
            correlation_id=telemetry.correlation_uuid(command.client_command_id),
            event_id=event_id,
            kind=EventKind.INBOX_THREAD_PROMOTED_TO_TICKET,
            origin=EventOrigin.API,
            payload=InboxThreadPromotedToTicketPayload(command.thread_id, command.ticket_id),
            prev_hash=last_hash,
            request_sha256=request_digest,
            sequence=command.expected_thread_version + 1,
            server_time=now,
            stream_id=f"inbox-thread:{command.thread_id}",
            tenant_id=actor.tenant_id,
        ),
        outbox_id,
    )


def _opened_event(
    actor: Actor,
    command: InboxSendCommand,
    sender: InboxParticipant,
    recipient: InboxParticipant,
    thread_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=thread_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=uuid7(now),
        kind=EventKind.INBOX_THREAD_OPENED,
        origin=EventOrigin.API,
        payload=InboxThreadOpenedPayload(sender, recipient, thread_id),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"inbox-thread:{thread_id}",
        tenant_id=actor.tenant_id,
    )


def _message_event(
    actor: Actor,
    command: InboxSendCommand,
    sender: InboxParticipant,
    recipient: InboxParticipant,
    *,
    thread_id: UUID,
    message_id: UUID,
    position: int,
    previous_hash: bytes,
    sequence: int,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=thread_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=message_id,
        kind=EventKind.INBOX_MESSAGE_APPENDED,
        origin=EventOrigin.API,
        payload=InboxMessageAppendedPayload(
            message_id, position, recipient, sender, command.text, thread_id
        ),
        prev_hash=previous_hash,
        request_sha256=request_digest,
        sequence=sequence,
        server_time=now,
        stream_id=f"inbox-thread:{thread_id}",
        tenant_id=actor.tenant_id,
    )
