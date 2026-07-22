"""Small deterministic Interface for the fixed I1 Routine subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

__all__ = [
    "CatchUpPolicy",
    "ConcurrencyPolicy",
    "FixedOperationJob",
    "OccurrenceOutcome",
    "OccurrencePlan",
    "Routine",
    "RoutineOccurrence",
    "RoutineRevision",
    "ScheduleKind",
    "SchedulerScan",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")
_FIXED_HANDLERS = frozenset({"synthetic_four_stage", "daily_backup", "record_anchor"})
_MAX_CATCH_UP = 100
_MAX_TIMEOUT_SECONDS = 86400


class ScheduleKind(StrEnum):
    DAILY = "daily"
    HOURLY = "hourly"


class ConcurrencyPolicy(StrEnum):
    COALESCE_IF_ACTIVE = "coalesce_if_active"
    SKIP_IF_ACTIVE = "skip_if_active"
    SERIALIZE_ONE_PENDING = "serialize_one_pending"
    ALWAYS_ENQUEUE_BOUNDED = "always_enqueue_bounded"


class CatchUpPolicy(StrEnum):
    SKIP_MISSED = "skip_missed"
    COALESCE_LATEST = "coalesce_latest"
    ENQUEUE_MISSED_WITH_CAP = "enqueue_missed_with_cap"


class OccurrenceOutcome(StrEnum):
    QUEUED = "queued"
    COALESCED = "coalesced"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class OccurrencePlan:
    scheduled_for: datetime
    local_civil_time: str
    utc_offset_seconds: int
    outcome: OccurrenceOutcome


@dataclass(frozen=True, slots=True)
class RoutineOccurrence:
    occurrence_id: UUID
    tenant_id: UUID
    routine_ref: str
    revision_digest: str
    scheduled_for: datetime
    local_civil_time: str
    timezone: str
    utc_offset_seconds: int
    outcome: OccurrenceOutcome
    job_id: UUID | None


@dataclass(frozen=True, slots=True)
class FixedOperationJob:
    job_id: UUID
    tenant_id: UUID
    occurrence_id: UUID
    operation: str
    timeout_seconds: int
    component_digests: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SchedulerScan:
    tenant_id: UUID
    scan_watermark: int
    observed_at: datetime
    occurrences: tuple[RoutineOccurrence, ...]
    jobs: tuple[FixedOperationJob, ...]


class _RoutineStore(Protocol):
    def register(
        self, tenant_id: UUID, revision: RoutineRevision, *, first_fire_at: datetime | None
    ) -> None: ...

    def scan(self, tenant_id: UUID) -> SchedulerScan: ...

    def tenant_ids(self) -> tuple[UUID, ...]: ...


class Routine:
    """Register exact revisions and scan due fixed jobs through one cohesive store."""

    def __init__(self, store: _RoutineStore) -> None:
        self._store = store

    def register(
        self,
        tenant_id: UUID,
        revision: RoutineRevision,
        *,
        first_fire_at: datetime | None = None,
    ) -> None:
        if first_fire_at is not None:
            _aware(first_fire_at)
        self._store.register(tenant_id, revision, first_fire_at=first_fire_at)

    def scan(self, tenant_id: UUID) -> SchedulerScan:
        return self._store.scan(tenant_id)

    def tenant_ids(self) -> tuple[UUID, ...]:
        return self._store.tenant_ids()


@dataclass(frozen=True, slots=True)
class RoutineRevision:
    """One digest-pinned fixed-operation schedule with wall-clock-once DST policy."""

    routine_ref: str
    revision_digest: str
    schedule_kind: ScheduleKind
    timezone: str
    local_time: time | None
    concurrency: ConcurrencyPolicy
    catch_up: CatchUpPolicy
    catch_up_cap: int
    handler_kind: str
    timeout_seconds: int
    component_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_revision_identity(self)
        _validate_revision_limits(self)
        _validate_revision_schedule(self)

    def next_fire_after(self, instant: datetime) -> datetime:
        """Return the next unique UTC instant, skipping nonexistent local times."""

        _aware(instant)
        if self.schedule_kind is ScheduleKind.HOURLY:
            current = instant.astimezone(UTC)
            return current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        zone = ZoneInfo(self.timezone)
        local_date = instant.astimezone(zone).date()
        for days in range(370):
            candidate = _wall_clock_once(local_date + timedelta(days=days), self.local_time, zone)
            if candidate is not None and candidate > instant:
                return candidate
        raise RuntimeError("daily Routine has no resolvable fire in the bounded calendar")

    def plan_due(
        self,
        due: tuple[datetime, ...],
        *,
        active_jobs: int = 0,
        pending_jobs: int = 0,
    ) -> tuple[OccurrencePlan, ...]:
        """Apply catch-up and concurrency to an already ordered due prefix."""

        if active_jobs < 0 or pending_jobs < 0:
            raise ValueError("Routine job counts cannot be negative")
        if tuple(sorted(due)) != due or len(set(due)) != len(due):
            raise ValueError("due Routine instants must be unique and ordered")
        outcomes = _catch_up_outcomes(self, len(due))
        outcomes = _concurrency_outcomes(self, outcomes, active_jobs, pending_jobs)
        return tuple(
            _plan(self, scheduled_for, outcome)
            for scheduled_for, outcome in zip(due, outcomes, strict=True)
        )


def _validate_revision_identity(revision: RoutineRevision) -> None:
    if _REFERENCE.fullmatch(revision.routine_ref) is None:
        raise ValueError("routine reference must be versioned")
    if _DIGEST.fullmatch(revision.revision_digest) is None:
        raise ValueError("routine revision digest must be content addressed")
    if not revision.component_digests or any(
        _DIGEST.fullmatch(item) is None for item in revision.component_digests
    ):
        raise ValueError("Routine components must be content addressed")
    if revision.handler_kind not in _FIXED_HANDLERS:
        raise ValueError("Routine handler is outside the fixed I1 subset")


def _validate_revision_limits(revision: RoutineRevision) -> None:
    if revision.catch_up_cap < 1 or revision.catch_up_cap > _MAX_CATCH_UP:
        raise ValueError("Routine catch-up cap is outside the bounded I1 range")
    if revision.timeout_seconds < 1 or revision.timeout_seconds > _MAX_TIMEOUT_SECONDS:
        raise ValueError("Routine timeout is outside the bounded I1 range")


def _validate_revision_schedule(revision: RoutineRevision) -> None:
    if revision.schedule_kind is ScheduleKind.DAILY and revision.local_time is None:
        raise ValueError("daily Routine requires a local civil time")
    if revision.local_time is not None and revision.local_time.tzinfo is not None:
        raise ValueError("Routine local civil time cannot carry an offset")
    try:
        ZoneInfo(revision.timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Routine timezone must be an installed IANA zone") from error


def _catch_up_outcomes(routine: RoutineRevision, count: int) -> tuple[OccurrenceOutcome, ...]:
    if count == 0:
        return ()
    older = count - 1
    if routine.catch_up is CatchUpPolicy.COALESCE_LATEST:
        return (OccurrenceOutcome.COALESCED,) * older + (OccurrenceOutcome.QUEUED,)
    queued = min(routine.catch_up_cap, count)
    return (OccurrenceOutcome.SKIPPED,) * (count - queued) + (OccurrenceOutcome.QUEUED,) * queued


def _concurrency_outcomes(
    routine: RoutineRevision,
    outcomes: tuple[OccurrenceOutcome, ...],
    active: int,
    pending: int,
) -> tuple[OccurrenceOutcome, ...]:
    busy = active + pending > 0
    replacement = OccurrenceOutcome.QUEUED
    if routine.concurrency is ConcurrencyPolicy.COALESCE_IF_ACTIVE and busy:
        replacement = OccurrenceOutcome.COALESCED
    elif routine.concurrency is ConcurrencyPolicy.SKIP_IF_ACTIVE and busy:
        replacement = OccurrenceOutcome.SKIPPED
    elif routine.concurrency is ConcurrencyPolicy.SERIALIZE_ONE_PENDING and pending > 0:
        replacement = OccurrenceOutcome.COALESCED
    return tuple(replacement if item is OccurrenceOutcome.QUEUED else item for item in outcomes)


def _plan(
    routine: RoutineRevision, scheduled_for: datetime, outcome: OccurrenceOutcome
) -> OccurrencePlan:
    _aware(scheduled_for)
    local = scheduled_for.astimezone(ZoneInfo(routine.timezone))
    offset = local.utcoffset()
    if offset is None:
        raise RuntimeError("Routine local offset is unavailable")
    return OccurrencePlan(
        scheduled_for=scheduled_for.astimezone(UTC),
        local_civil_time=local.replace(tzinfo=None).isoformat(),
        utc_offset_seconds=int(offset.total_seconds()),
        outcome=outcome,
    )


def _wall_clock_once(day: date, at: time | None, zone: ZoneInfo) -> datetime | None:
    if at is None:
        raise RuntimeError("daily Routine local time disappeared")
    naive = datetime.combine(day, at)
    candidates: set[datetime] = set()
    for fold in (0, 1):
        utc = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc)
    return min(candidates) if candidates else None


def _aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("Routine instants must be timezone-aware")
