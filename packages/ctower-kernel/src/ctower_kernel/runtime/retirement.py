"""Small public values for append-only fleet-beat retirement."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = ["BeatRoutineRetireCommand", "BeatRoutineRetirementReceipt"]

_BEAT_REFERENCE = re.compile(r"^ctower\.beat\.[a-z][a-z0-9._-]*@[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class BeatRoutineRetireCommand:
    client_command_id: UUID
    routine_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID):
            raise TypeError("beat retirement command ID must be a UUID")
        if _BEAT_REFERENCE.fullmatch(self.routine_ref) is None:
            raise ValueError("beat retirement requires a versioned fleet-beat reference")

    def request_payload(self) -> dict[str, object]:
        return {"routine_ref": self.routine_ref}


@dataclass(frozen=True, slots=True)
class BeatRoutineRetirementReceipt:
    command_id: UUID
    event_id: UUID
    retirement_id: UUID
    routine_ref: str
    revision_digest: str
    retired_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_id": str(self.event_id),
            "retired_at": self.retired_at.isoformat(),
            "retirement_id": str(self.retirement_id),
            "revision_digest": self.revision_digest,
            "routine_ref": self.routine_ref,
        }
