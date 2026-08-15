"""Small public value Interface for the closed typed activity-gate set."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ctower_kernel.runtime._routine_ids import stable_uuid7

__all__ = ["ActivityGate", "GateDecision", "GateOutcome"]

_GATE_KINDS = frozenset({"always", "new_movement_since_watermark", "open_tickets_above"})
_GATE_SOURCES = frozenset({"events", "tickets"})
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_MAX_THRESHOLD = 1_000_000


@dataclass(frozen=True, slots=True)
class ActivityGate:
    """Exactly one typed gate from the closed set; no expression language."""

    kind: str
    source: str | None = None
    threshold: int | None = None
    project_key: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in _GATE_KINDS:
            raise ValueError(f"activity gate kind is outside the closed gate set: {self.kind}")
        if self.kind == "always":
            self._validate_absent()
        elif self.kind == "new_movement_since_watermark":
            self._validate_movement()
        else:
            self._validate_threshold()

    def _validate_absent(self) -> None:
        if (self.source, self.threshold, self.project_key) != (None, None, None):
            raise ValueError("the always gate carries no parameters")

    def _validate_movement(self) -> None:
        if self.source not in _GATE_SOURCES:
            raise ValueError(f"activity gate source is outside the closed set: {self.source}")
        if self.threshold is not None or self.project_key is not None:
            raise ValueError("the movement gate carries only its source")

    def _validate_threshold(self) -> None:
        if self.source is not None and self.source != "tickets":
            raise ValueError("the ticket-count gate reads tickets only")
        if type(self.threshold) is not int or not 0 <= self.threshold <= _MAX_THRESHOLD:
            raise ValueError("activity gate threshold must be a bounded integer")
        if self.project_key is not None and _PROJECT_KEY.fullmatch(self.project_key) is None:
            raise ValueError(
                f"activity gate project key is outside the authored alphabet: {self.project_key}"
            )

    def watermark_kind(self) -> str:
        """Name the watermark this gate stands on."""

        if self.kind == "new_movement_since_watermark":
            if self.source == "events":
                return "events.server_time"
            return "tickets.server_time"
        if self.kind == "open_tickets_above":
            return "tickets.nonterminal"
        return "none"

    def canonical_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "source": self.source,
            "threshold": self.threshold,
            "project_key": self.project_key,
        }


class GateOutcome(StrEnum):
    FIRED = "fired"
    SKIPPED = "skipped"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class GateDecision:
    outcome: GateOutcome
    watermark_kind: str
    watermark_position: datetime | None
    observed_count: int
    detail: str

    @staticmethod
    def fact_identity(scheduled_for: datetime, *identity: bytes) -> UUID:
        """Deterministic evaluation-fact identity so exact replay appends nothing."""

        return stable_uuid7(scheduled_for, b"gate-evaluation", *identity)


def evaluate_gate(
    gate: ActivityGate,
    *,
    now: datetime,
    due: datetime,
    observed: int | None,
    watermark_position: datetime | None,
) -> GateDecision:
    """Fold one canonical read into the fire/skip/degraded decision.

    ``observed`` is the count the scheduled read produced; ``None`` means the
    read itself failed and the decision must degrade instead of firing clean.
    """

    del due  # the schedule already elapsed; the gate sees only its read
    if observed is None:
        return GateDecision(
            GateOutcome.DEGRADED,
            gate.watermark_kind(),
            watermark_position if isinstance(watermark_position, datetime) else None,
            -1,
            f"degraded read: {gate.kind} could not observe {gate.watermark_kind()}",
        )
    if gate.kind == "always":
        return GateDecision(GateOutcome.FIRED, "none", None, 0, "always gate")
    if gate.kind == "new_movement_since_watermark":
        moved = observed > 0
        if watermark_position is None:
            outcome = GateOutcome.FIRED
            detail = f"baseline evaluation observed {observed} rows on {gate.watermark_kind()}"
        elif moved:
            outcome = GateOutcome.FIRED
            detail = f"{observed} rows moved since {watermark_position.isoformat()}"
        else:
            outcome = GateOutcome.SKIPPED
            detail = f"no movement since {watermark_position.isoformat()}"
        return GateDecision(outcome, gate.watermark_kind(), watermark_position, observed, detail)
    threshold = gate.threshold or 0
    if observed > threshold:
        return GateDecision(
            GateOutcome.FIRED,
            gate.watermark_kind(),
            now,
            observed,
            f"{observed} nonterminal tickets above threshold {threshold}",
        )
    return GateDecision(
        GateOutcome.SKIPPED,
        gate.watermark_kind(),
        now,
        observed,
        f"{observed} nonterminal tickets at or below threshold {threshold}",
    )
