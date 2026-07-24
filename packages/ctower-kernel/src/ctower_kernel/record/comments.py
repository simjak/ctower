"""Typed authenticated ticket-comment command and replay result."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

__all__ = ["TicketCommentCommand", "TicketCommentResult"]

_MAX_COMMENT_BODY_LENGTH = 4_000


@dataclass(frozen=True, slots=True)
class TicketCommentCommand:
    client_command_id: UUID
    ticket_id: UUID
    body: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(self.ticket_id, UUID):
            raise TypeError("comment command identities must be UUIDs")
        if not 1 <= len(self.body) <= _MAX_COMMENT_BODY_LENGTH or not self.body.strip():
            raise ValueError("comment body must contain 1 to 4000 visible characters")

    def request_payload(self) -> dict[str, object]:
        return {"body": self.body, "ticket_id": str(self.ticket_id)}


@dataclass(frozen=True, slots=True)
class TicketCommentResult:
    command_id: UUID
    comment_id: UUID
    event_id: UUID
    ticket_id: UUID

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "comment_id": str(self.comment_id),
            "durability_state": "durability_pending",
            "event_id": str(self.event_id),
            "ticket_id": str(self.ticket_id),
        }
