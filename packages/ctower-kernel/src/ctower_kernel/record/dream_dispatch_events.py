"""Strict nightly-dream consumption event payload."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = ["DreamDispatchConsumedPayload"]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_MAX_REFERENCE_LENGTH = 128


@dataclass(frozen=True, slots=True)
class DreamDispatchConsumedPayload:
    effect_id: UUID
    lane_ref: str
    model_ref: str
    output_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.effect_id, UUID):
            raise TypeError("effect_id must be a UUID")
        _bounded("lane_ref", self.lane_ref)
        _bounded("model_ref", self.model_ref)
        if _DIGEST.fullmatch(self.output_digest) is None:
            raise ValueError("dream output digest must be content addressed")

    def to_mapping(self) -> dict[str, object]:
        return {
            "effect_id": str(self.effect_id),
            "lane_ref": self.lane_ref,
            "model_ref": self.model_ref,
            "output_digest": self.output_digest,
        }


def _bounded(label: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not 1 <= len(value) <= _MAX_REFERENCE_LENGTH:
        raise ValueError(f"{label} is outside the authored event contract")
