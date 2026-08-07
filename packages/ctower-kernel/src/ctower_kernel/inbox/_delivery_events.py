"""Typed delivery and read event construction for native inbox messages."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ctower_kernel.inbox.models import InboxAcknowledgeCommand, InboxAcknowledgementState
from ctower_kernel.record import Actor
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin, event_digest
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.inbox_events import (
    InboxMessageDeliveredPayload,
    InboxMessageReadPayload,
    InboxParticipant,
)
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def _acknowledgement_events(
    actor: Actor,
    command: InboxAcknowledgeCommand,
    recipient: InboxParticipant,
    *,
    thread_id: UUID,
    first_sequence: int,
    previous_hash: bytes,
    include_delivered: bool,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[EventEnvelope, ...]:
    events: list[EventEnvelope] = []
    states = (
        (InboxAcknowledgementState.DELIVERED, InboxAcknowledgementState.READ)
        if command.state is InboxAcknowledgementState.READ and include_delivered
        else (command.state,)
    )
    for offset, state in enumerate(states):
        payload = (
            InboxMessageDeliveredPayload(command.message_id, recipient, thread_id)
            if state is InboxAcknowledgementState.DELIVERED
            else InboxMessageReadPayload(command.message_id, recipient, thread_id)
        )
        event = EventEnvelope(
            actor_principal_id=actor.principal_id,
            aggregate_id=thread_id,
            causation_id=None,
            client_command_id=command.client_command_id,
            correlation_id=telemetry.correlation_uuid(command.client_command_id),
            event_id=uuid7(now),
            kind=(
                EventKind.INBOX_MESSAGE_DELIVERED
                if state is InboxAcknowledgementState.DELIVERED
                else EventKind.INBOX_MESSAGE_READ
            ),
            origin=EventOrigin.API,
            payload=payload,
            prev_hash=previous_hash,
            request_sha256=request_digest,
            sequence=first_sequence + offset,
            server_time=now,
            stream_id=f"inbox-thread:{thread_id}",
            tenant_id=actor.tenant_id,
        )
        events.append(event)
        previous_hash = event_digest(event)
    return tuple(events)
