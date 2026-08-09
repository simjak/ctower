"""Strict nightly-dream consumption event payload."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

__all__ = [
    "DreamDispatchConsumedPayload",
    "DreamLaneBoundPayload",
    "validate_dream_runtime_identity",
]

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


@dataclass(frozen=True, slots=True)
class DreamLaneBoundPayload:
    principal_id: UUID
    lane_ref: str
    crew_name: str
    harness_ref: str
    model_ref: str
    model_family: str
    reasoning_effort: str
    fallback_model_ref: str
    model_tier: str
    binding_source: str
    probe_evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.principal_id, UUID):
            raise TypeError("principal_id must be a UUID")
        for label in (
            "lane_ref",
            "crew_name",
            "harness_ref",
            "model_ref",
            "model_family",
            "reasoning_effort",
            "fallback_model_ref",
            "model_tier",
            "binding_source",
        ):
            _bounded(label, getattr(self, label))
        if _DIGEST.fullmatch(self.probe_evidence) is None:
            raise ValueError("dream lane probe evidence must be content addressed")

    def to_mapping(self) -> dict[str, object]:
        return {
            "binding_source": self.binding_source,
            "crew_name": self.crew_name,
            "fallback_model_ref": self.fallback_model_ref,
            "harness_ref": self.harness_ref,
            "lane_ref": self.lane_ref,
            "model_family": self.model_family,
            "model_ref": self.model_ref,
            "model_tier": self.model_tier,
            "principal_id": str(self.principal_id),
            "probe_evidence": self.probe_evidence,
            "reasoning_effort": self.reasoning_effort,
        }


def validate_dream_runtime_identity(aggregate_id: UUID, payload: object) -> None:
    """Keep dream effect and lane aggregates bound to their payload identity."""

    if isinstance(payload, DreamDispatchConsumedPayload) and aggregate_id != payload.effect_id:
        raise ValueError("dream dispatch aggregate and effect identity must match")
    if isinstance(payload, DreamLaneBoundPayload) and aggregate_id != payload.principal_id:
        raise ValueError("dream lane aggregate and principal identity must match")


def _bounded(label: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not 1 <= len(value) <= _MAX_REFERENCE_LENGTH:
        raise ValueError(f"{label} is outside the authored event contract")
