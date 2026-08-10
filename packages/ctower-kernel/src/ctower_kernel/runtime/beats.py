"""Small public value Interface for immutable fleet-beat dispatches."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = ["BeatDispatchEffect", "BeatDispatchSpec", "BeatRoutine"]

_MAX_PROMPT_BYTES = 16384
_TARGET_SESSIONS = frozenset({"commander", "mc-commander-manibo"})


@dataclass(frozen=True, slots=True)
class BeatDispatchSpec:
    beat_key: str
    prompt_source: str
    prompt_sha256: str
    prompt: str
    target_session: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"^[a-z][a-z0-9._-]*$", self.beat_key) is None:
            raise ValueError("beat key must be stable")
        if self.prompt_source != f"state/beats/{self.beat_key}.txt":
            raise ValueError("beat prompt source must match its stable key")
        if not self.prompt or len(self.prompt.encode("utf-8")) > _MAX_PROMPT_BYTES:
            raise ValueError("beat prompt must be present and bounded")
        expected = "sha256:" + hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()
        if self.prompt_sha256 != expected:
            raise ValueError("beat prompt digest must match baked content")
        if self.target_session not in _TARGET_SESSIONS:
            raise ValueError("fleet beats target a closed commander session")


@dataclass(frozen=True, slots=True)
class BeatDispatchEffect:
    effect_id: UUID
    occurrence_id: UUID
    tenant_id: UUID
    routine_ref: str
    revision_digest: str
    scheduled_for: datetime
    spec: BeatDispatchSpec
    emitted_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "effect_id": str(self.effect_id),
            "occurrence_id": str(self.occurrence_id),
            "routine_ref": self.routine_ref,
            "revision_digest": self.revision_digest,
            "scheduled_for": self.scheduled_for.isoformat(),
            "beat_key": self.spec.beat_key,
            "prompt_source": self.spec.prompt_source,
            "prompt_sha256": self.spec.prompt_sha256,
            "prompt": self.spec.prompt,
            "target_session": self.spec.target_session,
            "emitted_at": self.emitted_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class BeatRoutine:
    routine_ref: str
    revision_digest: str
    timezone: str
    minute_marks: tuple[int, ...]
    hour_marks: tuple[int, ...] | None
    beat_key: str
    prompt_source: str
    prompt_sha256: str
    target_session: str
    next_fire_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "routine_ref": self.routine_ref,
            "revision_digest": self.revision_digest,
            "schedule": {
                "kind": "minute_hour_set",
                "timezone": self.timezone,
                "minutes": list(self.minute_marks),
                "hours": list(self.hour_marks) if self.hour_marks is not None else None,
            },
            "beat_key": self.beat_key,
            "prompt_source": self.prompt_source,
            "prompt_sha256": self.prompt_sha256,
            "target_session": self.target_session,
            "next_fire_at": self.next_fire_at.isoformat(),
        }
