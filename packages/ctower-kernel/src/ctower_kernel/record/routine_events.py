"""Strict Routine retirement event payload."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = ["RoutineRetiredPayload", "validate_routine_retirement_identity"]

_BEAT_REFERENCE = re.compile(r"^ctower\.beat\.[a-z][a-z0-9._-]*@[1-9][0-9]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RoutineRetiredPayload:
    retirement_id: UUID
    routine_ref: str
    revision_digest: str
    retired_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.retirement_id, UUID):
            raise TypeError("Routine retirement ID must be a UUID")
        if _BEAT_REFERENCE.fullmatch(self.routine_ref) is None:
            raise ValueError("Routine retirement reference must name a fleet beat")
        if _DIGEST.fullmatch(self.revision_digest) is None:
            raise ValueError("Routine retirement revision must be content addressed")
        if not isinstance(self.retired_at, datetime) or self.retired_at.tzinfo is None:
            raise ValueError("Routine retirement time must be timezone-aware")

    def to_mapping(self) -> dict[str, object]:
        return {
            "retired_at": self.retired_at.isoformat(),
            "retirement_id": str(self.retirement_id),
            "revision_digest": self.revision_digest,
            "routine_ref": self.routine_ref,
        }


def validate_routine_retirement_identity(aggregate_id: UUID, payload: object) -> None:
    if isinstance(payload, RoutineRetiredPayload) and aggregate_id != payload.retirement_id:
        raise ValueError("Routine retirement aggregate and payload identity must match")
