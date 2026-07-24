"""Focused typed payloads for canonical ticket-stream events."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

__all__ = [
    "CustodyTransferredPayload",
    "TicketCommentAddedPayload",
    "TicketCreatedPayload",
    "TicketEventPayload",
    "ticket_payload_from_mapping",
]


@dataclass(frozen=True, slots=True)
class TicketCreatedPayload:
    custodian_id: UUID
    priority: str
    source_kind: str
    source_ref: str
    title: str

    def __post_init__(self) -> None:
        _uuid("custodian_id", self.custodian_id)
        if self.priority not in {"P0", "P1", "P2"}:
            raise ValueError("priority is outside the authored event contract")
        _bounded("source_kind", self.source_kind, minimum=1, maximum=64)
        _bounded("source_ref", self.source_ref, minimum=1, maximum=256)
        _bounded("title", self.title, minimum=1, maximum=200)

    def to_mapping(self) -> dict[str, object]:
        return {
            "custodian_id": str(self.custodian_id),
            "priority": self.priority,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class CustodyTransferredPayload:
    from_custodian_id: UUID
    reason: str
    to_custodian_id: UUID

    def __post_init__(self) -> None:
        _uuid("from_custodian_id", self.from_custodian_id)
        _uuid("to_custodian_id", self.to_custodian_id)
        _bounded("reason", self.reason, minimum=1, maximum=500)

    def to_mapping(self) -> dict[str, object]:
        return {
            "from_custodian_id": str(self.from_custodian_id),
            "reason": self.reason,
            "to_custodian_id": str(self.to_custodian_id),
        }


@dataclass(frozen=True, slots=True)
class TicketCommentAddedPayload:
    body: str
    comment_id: UUID
    ticket_id: UUID

    def __post_init__(self) -> None:
        _bounded("body", self.body, minimum=1, maximum=4000)
        if not self.body.strip():
            raise ValueError("comment body must contain visible text")
        _uuid("comment_id", self.comment_id)
        _uuid("ticket_id", self.ticket_id)

    def to_mapping(self) -> dict[str, object]:
        return {
            "body": self.body,
            "comment_id": str(self.comment_id),
            "ticket_id": str(self.ticket_id),
        }


type TicketEventPayload = (
    TicketCreatedPayload | CustodyTransferredPayload | TicketCommentAddedPayload
)


def ticket_payload_from_mapping(kind: str, payload: Mapping[str, object]) -> TicketEventPayload:
    if kind == "ticket.created":
        _require_keys(
            payload,
            {"custodian_id", "priority", "source_kind", "source_ref", "title"},
        )
        return TicketCreatedPayload(
            custodian_id=_uuid_value(payload["custodian_id"], "custodian_id"),
            priority=_string(payload["priority"], "priority"),
            source_kind=_string(payload["source_kind"], "source_kind"),
            source_ref=_string(payload["source_ref"], "source_ref"),
            title=_string(payload["title"], "title"),
        )
    if kind == "ticket.custody_transferred":
        _require_keys(payload, {"from_custodian_id", "reason", "to_custodian_id"})
        return CustodyTransferredPayload(
            from_custodian_id=_uuid_value(payload["from_custodian_id"], "from_custodian_id"),
            reason=_string(payload["reason"], "reason"),
            to_custodian_id=_uuid_value(payload["to_custodian_id"], "to_custodian_id"),
        )
    if kind == "ticket.comment_added":
        _require_keys(payload, {"body", "comment_id", "ticket_id"})
        return TicketCommentAddedPayload(
            body=_string(payload["body"], "body"),
            comment_id=_uuid_value(payload["comment_id"], "comment_id"),
            ticket_id=_uuid_value(payload["ticket_id"], "ticket_id"),
        )
    raise ValueError(f"{kind} is not a ticket timeline event")


def _bounded(label: str, value: object, *, minimum: int, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} is outside the authored event contract")


def _uuid(label: str, value: object) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{label} must be a UUID")


def _require_keys(payload: Mapping[str, object], expected: set[str]) -> None:
    if set(payload) != expected:
        raise ValueError("event payload fields do not match the authored variant")


def _uuid_value(value: object, label: str) -> UUID:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a UUID string")
    return UUID(value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value
