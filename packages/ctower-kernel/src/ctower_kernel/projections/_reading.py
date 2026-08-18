"""Shared source-reading primitives for projection folds.

Leaf module: `ReadingState`, `UnreachedScope`, and generic `SourceReading`
carry no projection-specific behaviour, so both the morning digest and the
movement fold can import them without a circular dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

__all__ = [
    "ReadingState",
    "SourceReading",
    "UnreachedScope",
]


class ReadingState(StrEnum):
    """Knowledge state of one source or rendered digest section."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class UnreachedScope:
    key: str
    reason: str

    def response_payload(self) -> dict[str, object]:
        return {"key": self.key, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class SourceReading[T]:
    """Rows that answered plus the exact scopes that did not."""

    state: ReadingState
    rows: tuple[T, ...]
    watermark: int | None
    observed_at: datetime
    unreached: tuple[UnreachedScope, ...] = ()

    def __post_init__(self) -> None:
        _validate_source_time(self.observed_at, self.watermark)
        _validate_source_state(self.state, self.rows, self.unreached)

    @classmethod
    def complete(
        cls,
        rows: tuple[T, ...],
        *,
        watermark: int,
        observed_at: datetime,
    ) -> SourceReading[T]:
        return cls(ReadingState.COMPLETE, rows, watermark, observed_at)

    @classmethod
    def partial(
        cls,
        rows: tuple[T, ...],
        *,
        watermark: int,
        observed_at: datetime,
        unreached: tuple[UnreachedScope, ...],
    ) -> SourceReading[T]:
        return cls(ReadingState.PARTIAL, rows, watermark, observed_at, unreached)

    @classmethod
    def unknown(
        cls,
        scope: UnreachedScope,
        *,
        observed_at: datetime,
    ) -> SourceReading[T]:
        return cls(ReadingState.UNKNOWN, (), None, observed_at, (scope,))


def _validate_source_time(observed_at: datetime, watermark: int | None) -> None:
    if observed_at.tzinfo is None:
        raise ValueError("source observation must be timezone-aware")
    if watermark is not None and watermark < 0:
        raise ValueError("source watermark cannot be negative")


def _validate_source_state(
    state: ReadingState,
    rows: tuple[object, ...],
    unreached: tuple[UnreachedScope, ...],
) -> None:
    if state is ReadingState.COMPLETE and unreached:
        raise ValueError("a complete reading cannot name an unreached scope")
    if state is ReadingState.PARTIAL and not unreached:
        raise ValueError("a partial reading must name an unreached scope")
    if state is ReadingState.UNKNOWN and (rows or not unreached):
        raise ValueError("an unknown reading carries no rows and names its failed scope")
