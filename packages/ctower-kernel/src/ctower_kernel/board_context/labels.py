"""Typed authenticated label-application command and replay result."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = ["ApplyLabelCommand", "ApplyLabelResult"]

_LABEL_KEY = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")


@dataclass(frozen=True, slots=True)
class ApplyLabelCommand:
    client_command_id: UUID
    ticket_id: UUID
    label_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID) or not isinstance(self.ticket_id, UUID):
            raise TypeError("apply-label command identities must be UUIDs")
        if _LABEL_KEY.fullmatch(self.label_key) is None:
            raise ValueError("label key is outside the authored contract")

    def request_payload(self) -> dict[str, object]:
        return {"label_key": self.label_key, "ticket_id": str(self.ticket_id)}


@dataclass(frozen=True, slots=True)
class ApplyLabelResult:
    command_id: UUID
    ticket_label_id: UUID
    event_id: UUID
    ticket_id: UUID
    label_key: str

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_id": str(self.event_id),
            "label_key": self.label_key,
            "ticket_id": str(self.ticket_id),
            "ticket_label_id": str(self.ticket_label_id),
        }
