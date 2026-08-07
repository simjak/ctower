"""Strict payloads for native inbox thread facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = [
    "INBOX_EVENT_TYPES",
    "InboxEventPayload",
    "InboxMessageAppendedPayload",
    "InboxMessageDeliveredPayload",
    "InboxMessageReadPayload",
    "InboxParticipant",
    "InboxThreadOpenedPayload",
    "InboxThreadPromotedToTicketPayload",
]

_SEAT_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_MAX_MESSAGE_LENGTH = 65536


@dataclass(frozen=True, slots=True)
class InboxParticipant:
    principal_id: UUID
    seat_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.principal_id, UUID):
            raise TypeError("inbox participant principal_id must be a UUID")
        if _SEAT_KEY.fullmatch(self.seat_key) is None:
            raise ValueError("inbox participant seat_key is outside the authored contract")

    def to_mapping(self) -> dict[str, object]:
        return {"principal_id": str(self.principal_id), "seat_key": self.seat_key}


@dataclass(frozen=True, slots=True)
class InboxThreadOpenedPayload:
    opener: InboxParticipant
    recipient: InboxParticipant
    thread_id: UUID

    def __post_init__(self) -> None:
        _validate_participants(self.opener, self.recipient)
        _thread_id(self.thread_id)

    def to_mapping(self) -> dict[str, object]:
        return {
            "opener": self.opener.to_mapping(),
            "recipient": self.recipient.to_mapping(),
            "thread_id": str(self.thread_id),
        }


@dataclass(frozen=True, slots=True)
class InboxMessageAppendedPayload:
    message_id: UUID
    position: int
    recipient: InboxParticipant
    sender: InboxParticipant
    text: str
    thread_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, UUID):
            raise TypeError("inbox message_id must be a UUID")
        if (
            not isinstance(self.position, int)
            or isinstance(self.position, bool)
            or self.position < 1
        ):
            raise ValueError("inbox message position must be positive")
        _validate_participants(self.sender, self.recipient)
        if not isinstance(self.text, str) or not 1 <= len(self.text) <= _MAX_MESSAGE_LENGTH:
            raise ValueError("inbox message text is outside the authored contract")
        _thread_id(self.thread_id)

    def to_mapping(self) -> dict[str, object]:
        return {
            "message_id": str(self.message_id),
            "position": self.position,
            "recipient": self.recipient.to_mapping(),
            "sender": self.sender.to_mapping(),
            "text": self.text,
            "thread_id": str(self.thread_id),
        }


@dataclass(frozen=True, slots=True)
class InboxMessageDeliveredPayload:
    message_id: UUID
    recipient: InboxParticipant
    thread_id: UUID

    def __post_init__(self) -> None:
        _validate_delivery_payload(self.message_id, self.recipient, self.thread_id)

    def to_mapping(self) -> dict[str, object]:
        return {
            "message_id": str(self.message_id),
            "recipient": self.recipient.to_mapping(),
            "thread_id": str(self.thread_id),
        }


@dataclass(frozen=True, slots=True)
class InboxMessageReadPayload:
    message_id: UUID
    recipient: InboxParticipant
    thread_id: UUID

    def __post_init__(self) -> None:
        _validate_delivery_payload(self.message_id, self.recipient, self.thread_id)

    def to_mapping(self) -> dict[str, object]:
        return {
            "message_id": str(self.message_id),
            "recipient": self.recipient.to_mapping(),
            "thread_id": str(self.thread_id),
        }


@dataclass(frozen=True, slots=True)
class InboxThreadPromotedToTicketPayload:
    thread_id: UUID
    ticket_id: UUID

    def __post_init__(self) -> None:
        _thread_id(self.thread_id)
        if not isinstance(self.ticket_id, UUID):
            raise TypeError("inbox ticket_id must be a UUID")

    def to_mapping(self) -> dict[str, object]:
        return {"thread_id": str(self.thread_id), "ticket_id": str(self.ticket_id)}


type InboxEventPayload = (
    InboxThreadOpenedPayload
    | InboxMessageAppendedPayload
    | InboxMessageDeliveredPayload
    | InboxMessageReadPayload
    | InboxThreadPromotedToTicketPayload
)

INBOX_EVENT_TYPES: tuple[tuple[str, type[object]], ...] = (
    ("thread.opened", InboxThreadOpenedPayload),
    ("message.appended", InboxMessageAppendedPayload),
    ("message.delivered", InboxMessageDeliveredPayload),
    ("message.read", InboxMessageReadPayload),
    ("thread.promoted_to_ticket", InboxThreadPromotedToTicketPayload),
)


def _validate_identity(payload: object, aggregate_id: UUID) -> None:
    if (
        isinstance(
            payload,
            InboxThreadOpenedPayload
            | InboxMessageAppendedPayload
            | InboxMessageDeliveredPayload
            | InboxMessageReadPayload
            | InboxThreadPromotedToTicketPayload,
        )
        and aggregate_id != payload.thread_id
    ):
        raise ValueError("inbox aggregate and thread identity must match")


def _validate_participants(sender: InboxParticipant, recipient: InboxParticipant) -> None:
    if not isinstance(sender, InboxParticipant) or not isinstance(recipient, InboxParticipant):
        raise TypeError("inbox participants must use InboxParticipant")
    if sender.principal_id == recipient.principal_id:
        raise ValueError("inbox participants must be distinct")


def _thread_id(value: object) -> None:
    if not isinstance(value, UUID):
        raise TypeError("inbox thread_id must be a UUID")


def _validate_delivery_payload(message_id: object, recipient: object, thread_id: object) -> None:
    if not isinstance(message_id, UUID):
        raise TypeError("inbox message_id must be a UUID")
    if not isinstance(recipient, InboxParticipant):
        raise TypeError("inbox recipient must use InboxParticipant")
    _thread_id(thread_id)
