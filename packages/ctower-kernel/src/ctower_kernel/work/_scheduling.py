"""Deterministic I1 priority-aging decision behind the Work Interface."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from ctower_kernel.work.interface import SchedulingCandidate

__all__: tuple[str, ...] = ()
AGING_STEP_SECONDS = 86_400
MAXIMUM_BOOST_LEVELS = 2
_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}


def schedule(
    candidates: tuple[SchedulingCandidate, ...], *, now: datetime
) -> tuple[tuple[UUID, ...], tuple[UUID, ...], tuple[UUID, ...]]:
    """Apply hard eligibility, bounded aging, and a stable total-order tie break."""

    if now.tzinfo is None:
        raise ValueError("scheduling clock must be timezone-aware")
    if len({candidate.ticket_id for candidate in candidates}) != len(candidates):
        raise ValueError("scheduling candidates must be unique")
    if any(candidate.priority not in _PRIORITY_RANK for candidate in candidates):
        raise ValueError("scheduling priority must be P0, P1, or P2")
    if any(candidate.eligible_since.tzinfo is None for candidate in candidates):
        raise ValueError("eligible_since must be timezone-aware")
    eligible = tuple(candidate for candidate in candidates if not candidate.unmet_eligibility)
    excluded = tuple(candidate for candidate in candidates if candidate.unmet_eligibility)
    ordered = tuple(sorted(eligible, key=lambda candidate: _key(candidate, now)))
    return (
        tuple(candidate.ticket_id for candidate in ordered),
        tuple(
            candidate.ticket_id
            for candidate in sorted(excluded, key=lambda item: item.ticket_id.int)
        ),
        tuple(candidate.ticket_id for candidate in ordered if candidate.checkpoint_verified),
    )


def _key(candidate: SchedulingCandidate, now: datetime) -> tuple[int, datetime, int]:
    age_seconds = max(0, int((now - candidate.eligible_since).total_seconds()))
    boost = min(MAXIMUM_BOOST_LEVELS, age_seconds // AGING_STEP_SECONDS)
    effective_rank = max(0, _PRIORITY_RANK[candidate.priority] - boost)
    return effective_rank, candidate.eligible_since, candidate.ticket_id.int
