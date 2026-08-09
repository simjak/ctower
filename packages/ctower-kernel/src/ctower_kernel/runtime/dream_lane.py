"""Typed operator ceremony for one immutable dream-lane binding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = ["DreamLaneBindCommand", "DreamLaneBindingReceipt"]

_CREW_NAME = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9._:-]{0,127}$")
_REQUIRED_SELECTION = ("codex", "gpt-5.6-sol", "max", "qwen3.8-max", "hard")


@dataclass(frozen=True, slots=True)
class DreamLaneBindCommand:
    client_command_id: UUID
    lane_ref: str
    crew_name: str
    harness_ref: str
    model_ref: str
    reasoning_effort: str
    fallback_model_ref: str
    model_tier: str

    def __post_init__(self) -> None:
        if not isinstance(self.client_command_id, UUID):
            raise TypeError("dream lane command ID must be a UUID")
        if _REFERENCE.fullmatch(self.lane_ref) is None:
            raise ValueError("dream lane reference is outside the ceremony contract")
        if _CREW_NAME.fullmatch(self.crew_name) is None:
            raise ValueError("dream crew name is outside the ceremony contract")
        selection = (
            self.harness_ref,
            self.model_ref,
            self.reasoning_effort,
            self.fallback_model_ref,
            self.model_tier,
        )
        if selection != _REQUIRED_SELECTION:
            raise ValueError("dream lane selection is outside the closed ceremony registry")

    def request_payload(self) -> dict[str, object]:
        return {
            "crew_name": self.crew_name,
            "fallback_model_ref": self.fallback_model_ref,
            "harness_ref": self.harness_ref,
            "lane_ref": self.lane_ref,
            "model_ref": self.model_ref,
            "model_tier": self.model_tier,
            "reasoning_effort": self.reasoning_effort,
        }


@dataclass(frozen=True, slots=True)
class DreamLaneBindingReceipt:
    command_id: UUID
    event_id: UUID
    principal_id: UUID
    lane_ref: str
    crew_name: str
    harness_ref: str
    model_ref: str
    model_family: str
    reasoning_effort: str
    model_tier: str
    binding_source: str
    probe_evidence: str
    bound_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "binding_source": self.binding_source,
            "bound_at": self.bound_at.isoformat(),
            "command_id": str(self.command_id),
            "crew_name": self.crew_name,
            "durability_state": "durability_pending",
            "event_id": str(self.event_id),
            "harness_ref": self.harness_ref,
            "lane_ref": self.lane_ref,
            "model_family": self.model_family,
            "model_ref": self.model_ref,
            "model_tier": self.model_tier,
            "principal_id": str(self.principal_id),
            "probe_evidence": self.probe_evidence,
            "reasoning_effort": self.reasoning_effort,
        }
