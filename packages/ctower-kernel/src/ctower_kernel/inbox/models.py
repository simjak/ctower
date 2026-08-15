"""Typed commands and committed results for the native inbox aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ctower_kernel.record.events import EventOrigin

__all__ = [
    "InboxAcknowledgeCommand",
    "InboxAcknowledgeResult",
    "InboxAcknowledgementState",
    "InboxPromotionCommand",
    "InboxPromotionOutcome",
    "InboxPromotionResult",
    "InboxSendCommand",
    "InboxSendResult",
]


class InboxAcknowledgementState(StrEnum):
    DELIVERED = "delivered"
    READ = "read"


class InboxPromotionOutcome(StrEnum):
    TICKET_CREATED = "ticket_created"
    TICKET_LINKED = "ticket_linked"


@dataclass(frozen=True, slots=True)
class InboxAcknowledgeCommand:
    client_command_id: UUID
    message_id: UUID
    state: InboxAcknowledgementState
    recorded_at: datetime | None = None
    origin: EventOrigin = EventOrigin.API

    def request_payload(self) -> dict[str, object]:
        return {"message_id": str(self.message_id), "state": self.state.value}


@dataclass(frozen=True, slots=True)
class InboxAcknowledgeResult:
    command_id: UUID
    delivered_at: datetime
    event_ids: tuple[UUID, ...]
    message_id: UUID
    read_at: datetime | None
    state: InboxAcknowledgementState
    thread_id: UUID
    thread_version: int

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "delivered_at": self.delivered_at.isoformat(),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "message_id": str(self.message_id),
            "read_at": self.read_at.isoformat() if self.read_at is not None else None,
            "state": self.state.value,
            "thread_id": str(self.thread_id),
            "thread_version": self.thread_version,
        }


@dataclass(frozen=True, slots=True)
class InboxSendCommand:
    client_command_id: UUID
    to: str
    text: str
    thread_id: UUID | None = None
    message_id: UUID | None = None
    sent_at: datetime | None = None
    source_ref: str | None = None
    source_sender: str | None = None
    source_recipient: str | None = None
    sender_principal_id: UUID | None = None
    sender_seat: str | None = None
    origin: EventOrigin = EventOrigin.API

    def request_payload(self) -> dict[str, object]:
        return {
            "text": self.text,
            "thread_id": str(self.thread_id) if self.thread_id is not None else None,
            "to": self.to,
        }


@dataclass(frozen=True, slots=True)
class InboxSendResult:
    command_id: UUID
    event_ids: tuple[UUID, ...]
    from_seat: str
    message_id: UUID
    position: int
    sent_at: datetime
    thread_id: UUID
    thread_version: int
    to: str

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "from": self.from_seat,
            "message_id": str(self.message_id),
            "position": self.position,
            "sent_at": self.sent_at.isoformat(),
            "thread_id": str(self.thread_id),
            "thread_version": self.thread_version,
            "to": self.to,
        }


@dataclass(frozen=True, slots=True)
class InboxPromotionCommand:
    client_command_id: UUID
    thread_id: UUID
    ticket_id: UUID | None = None

    def request_payload(self) -> dict[str, object]:
        return {
            "thread_id": str(self.thread_id),
            "ticket_id": str(self.ticket_id) if self.ticket_id is not None else None,
        }


@dataclass(frozen=True, slots=True)
class InboxPromotionResult:
    command_id: UUID
    event_ids: tuple[UUID, ...]
    outcome: InboxPromotionOutcome
    thread_id: UUID
    thread_version: int
    ticket_id: UUID

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "outcome": self.outcome.value,
            "thread_id": str(self.thread_id),
            "thread_version": self.thread_version,
            "ticket_id": str(self.ticket_id),
        }
