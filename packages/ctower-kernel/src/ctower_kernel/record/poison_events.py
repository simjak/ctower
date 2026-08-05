"""Strict Poison-disposition event payload, kept separate from Record envelope mechanics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = ["PoisonDispositionRecordedPayload"]

_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
_MAX_REASON_LENGTH = 500


@dataclass(frozen=True, slots=True)
class PoisonDispositionRecordedPayload:
    outbox_id: UUID
    consumer_key: str
    topic: str
    action: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.outbox_id, UUID):
            raise TypeError("outbox_id must be a UUID")
        if _STABLE_KEY.fullmatch(self.consumer_key) is None:
            raise ValueError("poison consumer key is outside the authored event contract")
        if _STABLE_KEY.fullmatch(self.topic) is None:
            raise ValueError("poison topic is outside the authored event contract")
        if self.action not in {"retry", "tombstone"}:
            raise ValueError("poison action is outside the authored event contract")
        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string")
        if not 1 <= len(self.reason) <= _MAX_REASON_LENGTH:
            raise ValueError("reason is outside the authored event contract")

    def to_mapping(self) -> dict[str, object]:
        return {
            "action": self.action,
            "consumer_key": self.consumer_key,
            "outbox_id": str(self.outbox_id),
            "reason": self.reason,
            "topic": self.topic,
        }
