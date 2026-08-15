"""Movement read fold: deterministic counts for the digest from transition facts.

Movement facts are Ticket-linked transition facts, never exhaustive Ticket
snapshots.  This module folds accepted transition-fact rows into a small digest
summary — counts grouped by Project and exact from/to stage, one pointer to the
movement view, and a source watermark — without embedding event rows, Ticket
identity, or Ticket text.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ctower_kernel.projections._reading import ReadingState, SourceReading

__all__ = [
    "MovementCountInput",
    "MovementDigestCount",
    "MovementDigestSummary",
    "derive_movement_summary",
]

_VILNIUS = ZoneInfo("Europe/Vilnius")
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
_STAGE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
_POINTER = "/v1/projects/{project_key}/movement"


@dataclass(frozen=True, slots=True)
class MovementCountInput:
    """One accepted transition fact that counts as a movement."""

    project_key: str
    source_stage: str
    stage: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if _PROJECT_KEY.fullmatch(self.project_key) is None:
            raise ValueError("movement project key must be stable")
        if _STAGE_KEY.fullmatch(self.source_stage) is None:
            raise ValueError("movement source stage must be stable")
        if _STAGE_KEY.fullmatch(self.stage) is None:
            raise ValueError("movement stage must be stable")
        if self.occurred_at.tzinfo is None:
            raise ValueError("movement observation must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MovementDigestCount:
    """One deterministic (project, from, to) bucket plus its measured count."""

    project_key: str
    from_stage: str
    to_stage: str
    count: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("movement count must be positive")
        if _PROJECT_KEY.fullmatch(self.project_key) is None:
            raise ValueError("movement project key must be stable")
        if _STAGE_KEY.fullmatch(self.from_stage) is None:
            raise ValueError("movement source stage must be stable")
        if _STAGE_KEY.fullmatch(self.to_stage) is None:
            raise ValueError("movement to stage must be stable")

    def response_payload(self) -> dict[str, object]:
        return {
            "count": self.count,
            "from_stage": self.from_stage,
            "project_key": self.project_key,
            "to_stage": self.to_stage,
        }


@dataclass(frozen=True, slots=True)
class MovementDigestSummary:
    """Digest-safe movement counts plus pointer, watermark, and completeness."""

    digest_date: date
    stored_counts: tuple[MovementDigestCount, ...]
    watermark: int | None
    state: ReadingState
    unreached_scopes: tuple[str, ...]

    @property
    def pointer(self) -> str:
        return _POINTER

    @property
    def source_state(self) -> str:
        if self.state is ReadingState.UNKNOWN:
            return "unavailable"
        return self.state.value

    def counts(self) -> dict[tuple[str, str, str], int]:
        return {
            (item.project_key, item.from_stage, item.to_stage): item.count
            for item in self.stored_counts
        }

    def response_payload(self) -> dict[str, object]:
        return {
            "counts": [item.response_payload() for item in self.stored_counts],
            "pointer": self.pointer,
            "source_state": self.source_state,
            "unreached_scopes": list(self.unreached_scopes),
            "watermark": self.watermark,
        }


def derive_movement_summary(
    reading: SourceReading[MovementCountInput],
    *,
    digest_date: date,
) -> MovementDigestSummary:
    """Fold a movement source reading into a deterministic digest summary.

    Only transition facts recorded within the prior Europe/Vilnius civil day
    count as movement.  Absence stays absence: an unreached or unknown source
    yields no measured counts (never a false zero) and keeps its named scope.
    """

    if reading.watermark is not None and reading.watermark < 0:
        raise ValueError("movement watermark cannot be negative")
    start = datetime.combine(digest_date - timedelta(days=1), time.min, _VILNIUS)
    end = datetime.combine(digest_date, time.min, _VILNIUS)
    counts = Counter(
        (item.project_key, item.source_stage, item.stage)
        for item in reading.rows
        if start <= item.occurred_at.astimezone(_VILNIUS) < end
    )
    staged = tuple(
        sorted(
            (
                MovementDigestCount(project, source, stage, count)
                for (project, source, stage), count in counts.items()
            ),
            key=lambda item: (item.project_key, item.from_stage, item.to_stage),
        )
    )
    unreached_scopes = tuple(sorted(f"{scope.key}:{scope.reason}" for scope in reading.unreached))
    return MovementDigestSummary(
        digest_date=digest_date,
        stored_counts=staged,
        watermark=reading.watermark,
        state=reading.state,
        unreached_scopes=unreached_scopes,
    )
