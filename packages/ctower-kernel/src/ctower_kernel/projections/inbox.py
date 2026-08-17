"""Native inbox delivery and read projection values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ctower_kernel.record.inbox_events import InboxSeverity

__all__ = ["InboxDeliveryState", "InboxMessageReadState", "InboxReadState"]


class InboxDeliveryState(StrEnum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


@dataclass(frozen=True, slots=True)
class InboxMessageReadState:
    delivered_at: datetime | None
    delivered_event_id: UUID | None
    message_id: UUID
    position: int
    read_at: datetime | None
    read_event_id: UUID | None
    recipient: str
    state: InboxDeliveryState
    severity: InboxSeverity = InboxSeverity.INFO

    def __post_init__(self) -> None:
        try:
            severity = InboxSeverity(self.severity)
        except ValueError as error:
            raise ValueError("inbox message severity is outside the authored contract") from error
        object.__setattr__(self, "severity", severity)

    def response_payload(self) -> dict[str, object]:
        return {
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "delivered_event_id": (
                str(self.delivered_event_id) if self.delivered_event_id else None
            ),
            "message_id": str(self.message_id),
            "position": self.position,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "read_event_id": str(self.read_event_id) if self.read_event_id else None,
            "recipient": self.recipient,
            "severity": self.severity.value,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True)
class InboxReadState:
    messages: tuple[InboxMessageReadState, ...]
    thread_id: UUID

    def response_payload(self) -> dict[str, object]:
        return {
            "messages": [item.response_payload() for item in self.messages],
            "thread_id": str(self.thread_id),
        }
