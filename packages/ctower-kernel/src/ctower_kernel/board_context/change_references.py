"""Typed authenticated ticket change-reference command and replay result."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

__all__ = ["ChangeReferenceCommand", "ChangeReferenceResult"]

_MAX_REPOSITORY_LENGTH = 256
_MAX_CHANGE_IDENTITY_LENGTH = 128
_MAX_REFERENCE_LENGTH = 256


@dataclass(frozen=True, slots=True)
class ChangeReferenceCommand:
    client_command_id: UUID
    ticket_id: UUID
    repository: str
    change_identity: str
    reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(self.ticket_id, UUID):
            raise TypeError("change reference command identities must be UUIDs")
        if not 1 <= len(self.repository) <= _MAX_REPOSITORY_LENGTH:
            raise ValueError("change reference repository is outside the authored contract")
        if not 1 <= len(self.change_identity) <= _MAX_CHANGE_IDENTITY_LENGTH:
            raise ValueError("change reference identity is outside the authored contract")
        if not 1 <= len(self.reference) <= _MAX_REFERENCE_LENGTH:
            raise ValueError("change reference is outside the authored contract")

    def request_payload(self) -> dict[str, object]:
        return {
            "change_identity": self.change_identity,
            "reference": self.reference,
            "repository": self.repository,
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class ChangeReferenceResult:
    command_id: UUID
    change_reference_id: UUID
    event_id: UUID
    ticket_id: UUID

    def response_payload(self) -> dict[str, object]:
        return {
            "change_reference_id": str(self.change_reference_id),
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_id": str(self.event_id),
            "ticket_id": str(self.ticket_id),
        }
