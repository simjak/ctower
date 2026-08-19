"""What the ledger must model about resilience, so it stays faithful to what happened.

Resilience is not free and this is where that becomes visible. A rotation resets the
provider's prompt cache: one full-price context re-read. A cross-provider fallback resets it
twice — switching away and switching back. A fallback is therefore an **event within a
turn**, never a mode: a ledger that recorded it as a state would report a seat as "on the
fallback" for an hour when it was there for one turn.

Layer identity is preserved on every row. Layer 1 is the same subscription serving again;
layer 2 is a different vendor answering. Collapsing them is how a cross-provider failover
gets recorded as a rotation and a judgment lane quietly changes family.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

__all__ = [
    "FALLBACK_CONTEXT_REREADS",
    "ROTATION_CONTEXT_REREADS",
    "CostEvent",
    "TurnLedger",
    "bypasses_explicit_provider",
]

# One rotation = one context re-read. One fallback activation = two: switch and return.
ROTATION_CONTEXT_REREADS = 1
FALLBACK_CONTEXT_REREADS = 2

# A capacity error means this provider cannot serve at all, so an explicitly configured
# provider is bypassed. A transient error means it can, so the explicit choice is respected.
_CAPACITY_CODES: frozenset[str] = frozenset({"402", "daily-quota", "connection"})


@dataclass(frozen=True, slots=True)
class CostEvent:
    """One metered event, attributed to the layer it happened on."""

    kind: Literal["rotation", "fallback_activation", "retry_skipped", "degradation"]
    layer: Literal["pool", "fallback", "none"]
    turn_id: str
    context_rereads: int
    detail: str
    at: datetime

    def to_mapping(self) -> dict[str, object]:
        return {
            "at": self.at.isoformat(),
            "context_rereads": self.context_rereads,
            "detail": self.detail,
            "kind": self.kind,
            "layer": self.layer,
            "turn_id": self.turn_id,
        }


@dataclass(slots=True)
class TurnLedger:
    """Cost events for one seat and attempt, with fallback held to one per turn."""

    events: list[CostEvent] = field(default_factory=list)
    _activated_turns: set[str] = field(default_factory=set)

    def rotation(self, *, turn_id: str, entry_identity: str | None, at: datetime) -> CostEvent:
        """Meter a same-provider rotation. Never recorded as a cross-provider fallback."""

        return self._append(
            CostEvent(
                kind="rotation",
                layer="pool",
                turn_id=turn_id,
                context_rereads=ROTATION_CONTEXT_REREADS,
                detail=f"rotated within the provider to {entry_identity or 'an unnamed entry'}",
                at=at,
            )
        )

    def fallback(self, *, turn_id: str, provider_key: str, at: datetime) -> CostEvent | None:
        """Meter one cross-provider activation, or `None` if this turn already had one."""

        if turn_id in self._activated_turns:
            return None
        self._activated_turns.add(turn_id)
        return self._append(
            CostEvent(
                kind="fallback_activation",
                layer="fallback",
                turn_id=turn_id,
                context_rereads=FALLBACK_CONTEXT_REREADS,
                detail=f"activated {provider_key} for this turn and returned to the primary",
                at=at,
            )
        )

    def retry_skipped(self, *, turn_id: str, reset_at: datetime, at: datetime) -> CostEvent:
        """State the skip. An absent retry is otherwise indistinguishable from a bug."""

        return self._append(
            CostEvent(
                kind="retry_skipped",
                layer="none",
                turn_id=turn_id,
                context_rereads=0,
                detail=f"did not retry primary: reset_at {reset_at.isoformat()} unelapsed",
                at=at,
            )
        )

    def degradation(self, *, turn_id: str, detail: str, at: datetime) -> CostEvent:
        """A degraded state must never render as a healthy one."""

        return self._append(
            CostEvent(
                kind="degradation",
                layer="none",
                turn_id=turn_id,
                context_rereads=0,
                detail=detail,
                at=at,
            )
        )

    def context_rereads(self) -> int:
        return sum(event.context_rereads for event in self.events)

    def _append(self, event: CostEvent) -> CostEvent:
        self.events.append(event)
        return event


def bypasses_explicit_provider(error_code: str) -> bool:
    """Whether this error class overrides an explicitly configured provider."""

    return error_code in _CAPACITY_CODES
