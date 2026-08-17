"""Native inbox delivery and read projection values."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

__all__ = [
    "InboxCorrespondent",
    "InboxCorrespondentList",
    "InboxDeliveryState",
    "InboxMessage",
    "InboxMessageReadState",
    "InboxReadState",
    "InboxThread",
    "InboxThreadList",
    "InboxThreadSummary",
]


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


@dataclass(frozen=True, slots=True)
class InboxThreadSummary:
    last_message_at: datetime
    last_message_preview: str
    other_agent: str
    promoted_ticket_id: UUID | None
    thread_id: UUID
    unread_count: int

    def response_payload(self) -> dict[str, object]:
        return {
            "last_message_at": self.last_message_at.isoformat(),
            "last_message_preview": self.last_message_preview,
            "other_agent": self.other_agent,
            "promoted_ticket_id": (
                str(self.promoted_ticket_id) if self.promoted_ticket_id is not None else None
            ),
            "thread_id": str(self.thread_id),
            "unread_count": self.unread_count,
        }


@dataclass(frozen=True, slots=True)
class InboxThreadList:
    recipient: str
    threads: tuple[InboxThreadSummary, ...]
    total_unread: int
    unread_only: bool

    def response_payload(self) -> dict[str, object]:
        return {
            "recipient": self.recipient,
            "threads": [item.response_payload() for item in self.threads],
            "total_unread": self.total_unread,
            "unread_only": self.unread_only,
        }


@dataclass(frozen=True, slots=True)
class InboxCorrespondent:
    project_key: str
    seat_key: str

    def response_payload(self) -> dict[str, object]:
        return {"project_key": self.project_key, "seat_key": self.seat_key}


@dataclass(frozen=True, slots=True)
class InboxCorrespondentList:
    """Every address the authenticated principal can open a thread to, and its own seat.

    These are fewer than the registered seats, and that is the point: the send
    command resolves a recipient by ``(tenant_id, seat_key)``, so a key two
    seats share resolves to nobody, the reader's own seat resolves to itself,
    and a reader with no seat row cannot send at all. Each of those is left out
    here for the same reason the command refuses it, so a picker built on this
    list can offer nothing the record would not accept as an address. ``sender``
    is ``unaddressable`` exactly when this principal holds no seat row.
    """

    correspondents: tuple[InboxCorrespondent, ...]
    sender: str

    def response_payload(self) -> dict[str, object]:
        return {
            "correspondents": [item.response_payload() for item in self.correspondents],
            "sender": self.sender,
        }


@dataclass(frozen=True, slots=True)
class InboxMessage:
    from_seat: str
    message_id: UUID
    position: int
    sent_at: datetime
    text: str
    to: str

    def response_payload(self) -> dict[str, object]:
        return {
            "from": self.from_seat,
            "message_id": str(self.message_id),
            "position": self.position,
            "sent_at": self.sent_at.isoformat(),
            "text": self.text,
            "to": self.to,
        }


@dataclass(frozen=True, slots=True)
class InboxThread:
    messages: tuple[InboxMessage, ...]
    participants: tuple[str, str]
    promoted_ticket_id: UUID | None
    read_through_position: int
    thread_id: UUID

    def response_payload(self) -> dict[str, object]:
        return {
            "messages": [item.response_payload() for item in self.messages],
            "participants": list(self.participants),
            "promoted_ticket_id": (
                str(self.promoted_ticket_id) if self.promoted_ticket_id is not None else None
            ),
            "read_through_position": self.read_through_position,
            "thread_id": str(self.thread_id),
        }
