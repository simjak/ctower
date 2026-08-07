"""Typed commands and committed results for the native inbox aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = [
    "InboxPromotionCommand",
    "InboxPromotionResult",
    "InboxSendCommand",
    "InboxSendResult",
]


@dataclass(frozen=True, slots=True)
class InboxSendCommand:
    client_command_id: UUID
    to: str
    text: str
    thread_id: UUID | None = None

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
    expected_thread_version: int
    thread_id: UUID
    ticket_id: UUID

    def request_payload(self) -> dict[str, object]:
        return {
            "expected_thread_version": self.expected_thread_version,
            "thread_id": str(self.thread_id),
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class InboxPromotionResult:
    command_id: UUID
    event_id: UUID
    thread_id: UUID
    thread_version: int
    ticket_id: UUID

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(self.event_id)],
            "thread_id": str(self.thread_id),
            "thread_version": self.thread_version,
            "ticket_id": str(self.ticket_id),
        }
