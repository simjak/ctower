"""Typed canonical payloads for append-only Routine lifecycle facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = ["RoutineRetiredPayload"]

_BEAT_REFERENCE = re.compile(r"^ctower\.beat\.[a-z][a-z0-9._-]*@[1-9][0-9]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RoutineRetiredPayload:
    retirement_id: UUID
    routine_ref: str
    revision_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.retirement_id, UUID):
            raise TypeError("Routine retirement identity must be a UUID")
        if _BEAT_REFERENCE.fullmatch(self.routine_ref) is None:
            raise ValueError("retired Routine reference must name a fleet beat")
        if _DIGEST.fullmatch(self.revision_digest) is None:
            raise ValueError("retired Routine revision must be content addressed")

    def to_mapping(self) -> dict[str, object]:
        return {
            "retirement_id": str(self.retirement_id),
            "revision_digest": self.revision_digest,
            "routine_ref": self.routine_ref,
        }
