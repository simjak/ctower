"""Small deterministic Interface for the fixed I1 Routine subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ctower_kernel.runtime.gates import ActivityGate
from ctower_kernel.runtime.items import (
    CompleteRoutineWorkItemCommand,
    RoutineAlarmEpisode,
    RoutineItemSpec,
    RoutineWorkItem,
    RoutineWorkItemAlarm,
    RoutineWorkItemReceipt,
    RoutineWorkItemSuppression,
)

if TYPE_CHECKING:
    from ctower_kernel.record import Actor, RecordProblem

__all__ = [
    "CatchUpPolicy",
    "ConcurrencyPolicy",
    "DreamDispatchConsumeCommand",
    "DreamDispatchConsumption",
    "DreamDispatchEffect",
    "DreamDispatchReceipt",
    "DreamDispatchSpec",
    "FixedOperationAttempt",
    "FixedOperationCompletion",
    "FixedOperationJob",
    "FixedOperationResult",
    "FixedOperations",
    "OccurrenceOutcome",
    "OccurrencePlan",
    "Routine",
    "RoutineOccurrence",
    "RoutineRevision",
    "ScheduleKind",
    "ScheduleOffsetDecision",
    "SchedulerScan",
    "SyntheticRun",
    "SyntheticRunCommand",
    "SyntheticRunReceipt",
    "SyntheticRunState",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")
_FIXED_HANDLERS = frozenset({"synthetic_four_stage", "daily_backup", "record_anchor"})
_HANDLERS = _FIXED_HANDLERS | {"dream_dispatch", "routine_item"}
_MAX_CATCH_UP = 100
_MAX_TIMEOUT_SECONDS = 86400
_MAX_MINUTE_MARK = 59
_MAX_HOUR_MARK = 23


class ScheduleKind(StrEnum):
    DAILY = "daily"
    HOURLY = "hourly"
    MINUTE_HOUR_SET = "minute_hour_set"


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
    REFUSED = "refused"


class ScheduleOffsetDecision(StrEnum):
    EXACT = "exact"
    EARLIER_OFFSET = "earlier_offset"
    NONEXISTENT_LOCAL_TIME = "nonexistent_local_time"


@dataclass(frozen=True, slots=True)
class OccurrencePlan:
    scheduled_for: datetime
    local_civil_time: str
    utc_offset_seconds: int | None
    offset_decision: ScheduleOffsetDecision
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
    utc_offset_seconds: int | None
    offset_decision: ScheduleOffsetDecision
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
class DreamDispatchSpec:
    scope_kind: str
    project_key: str | None
    skill_path: str
    primary_model_ref: str
    primary_reasoning_effort: str
    fallback_model_ref: str
    fallback_reasoning_effort: str
    minimum_model_tier: str
    excluded_model_families: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.scope_kind not in {"project", "fleet"} or (self.scope_kind == "project") != (
            self.project_key is not None
        ):
            raise ValueError("dream scope and project identity do not match")
        if self.skill_path != "skills/dreamer/SKILL.md":
            raise ValueError("dream dispatch must pin the authored dreamer skill")
        requirement = (
            self.primary_model_ref,
            self.primary_reasoning_effort,
            self.fallback_model_ref,
            self.fallback_reasoning_effort,
            self.minimum_model_tier,
            self.excluded_model_families,
        )
        if requirement != ("gpt-5.6-sol", "max", "qwen3.8-max", "max", "hard", ("claude",)):
            raise ValueError("dream dispatch model requirement is outside gh#368")


@dataclass(frozen=True, slots=True)
class DreamDispatchEffect:
    effect_id: UUID
    occurrence_id: UUID
    tenant_id: UUID
    routine_ref: str
    revision_digest: str
    scheduled_for: datetime
    spec: DreamDispatchSpec
    emitted_at: datetime
    consumption: DreamDispatchConsumption | None = None

    def response_payload(self) -> dict[str, object]:
        return {
            "effect_id": str(self.effect_id),
            "occurrence_id": str(self.occurrence_id),
            "routine_ref": self.routine_ref,
            "revision_digest": self.revision_digest,
            "scheduled_for": self.scheduled_for.isoformat(),
            "scope": {"kind": self.spec.scope_kind, "project_key": self.spec.project_key},
            "skill_path": self.spec.skill_path,
            "model_requirement": {
                "primary": {
                    "model_ref": self.spec.primary_model_ref,
                    "reasoning_effort": self.spec.primary_reasoning_effort,
                },
                "fallback": {
                    "model_ref": self.spec.fallback_model_ref,
                    "reasoning_effort": self.spec.fallback_reasoning_effort,
                },
                "minimum_tier": self.spec.minimum_model_tier,
                "excluded_families": list(self.spec.excluded_model_families),
            },
            "emitted_at": self.emitted_at.isoformat(),
            "consumption": self.consumption.response_payload() if self.consumption else None,
        }


@dataclass(frozen=True, slots=True)
class DreamDispatchConsumption:
    executor_principal_id: UUID
    lane_ref: str
    crew_name: str
    harness_ref: str
    model_ref: str
    model_family: str
    reasoning_effort: str
    model_tier: str
    consumed_at: datetime
    output_digest: str

    def response_payload(self) -> dict[str, object]:
        return {
            "executor_principal_id": str(self.executor_principal_id),
            "lane_ref": self.lane_ref,
            "crew_name": self.crew_name,
            "harness_ref": self.harness_ref,
            "model_ref": self.model_ref,
            "model_family": self.model_family,
            "reasoning_effort": self.reasoning_effort,
            "model_tier": self.model_tier,
            "consumed_at": self.consumed_at.isoformat(),
            "output_digest": self.output_digest,
        }


@dataclass(frozen=True, slots=True)
class DreamDispatchConsumeCommand:
    client_command_id: UUID
    effect_id: UUID
    output_digest: str

    def __post_init__(self) -> None:
        if _DIGEST.fullmatch(self.output_digest) is None:
            raise ValueError("dream output digest must be content addressed")

    def request_payload(self) -> dict[str, object]:
        return {"effect_id": str(self.effect_id), "output_digest": self.output_digest}


@dataclass(frozen=True, slots=True)
class DreamDispatchReceipt:
    command_id: UUID
    event_id: UUID
    effect_id: UUID
    output_digest: str

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "effect_id": str(self.effect_id),
            "durability_state": "durability_pending",
            "event_id": str(self.event_id),
            "output_digest": self.output_digest,
        }


class SyntheticRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SyntheticRunCommand:
    client_command_id: UUID
    workflow_ref: str

    def request_payload(self) -> dict[str, object]:
        return {"workflow_ref": self.workflow_ref}


@dataclass(frozen=True, slots=True)
class SyntheticRunReceipt:
    command_id: UUID
    event_ids: tuple[UUID, ...]
    run_id: UUID
    job_id: UUID
    workflow_ref: str

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "job_id": str(self.job_id),
            "run_id": str(self.run_id),
            "workflow_ref": self.workflow_ref,
        }


@dataclass(frozen=True, slots=True)
class FixedOperationAttempt:
    attempt_id: UUID
    job: FixedOperationJob
    attempt_number: int
    fencing_token: UUID
    worker_ref: str
    claimed_at: datetime
    claim_expires_at: datetime


@dataclass(frozen=True, slots=True)
class FixedOperationCompletion:
    succeeded: bool
    ticket_id: UUID | None
    lifecycle_facts: tuple[str, ...]
    detail_code: str


@dataclass(frozen=True, slots=True)
class FixedOperationResult:
    result_id: UUID
    job_id: UUID
    attempt_id: UUID
    fencing_token: UUID
    state: SyntheticRunState
    ticket_id: UUID | None
    lifecycle_facts: tuple[str, ...]
    detail_code: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class SyntheticRun:
    run_id: UUID
    job_id: UUID
    workflow_ref: str
    state: SyntheticRunState
    attempt_count: int
    ticket_id: UUID | None
    lifecycle_facts: tuple[str, ...]
    detail_code: str | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class SchedulerScan:
    tenant_id: UUID
    scan_watermark: int
    observed_at: datetime
    occurrences: tuple[RoutineOccurrence, ...]
    jobs: tuple[FixedOperationJob, ...]
    dream_dispatches: tuple[DreamDispatchEffect, ...] = ()
    work_items: tuple[RoutineWorkItem, ...] = ()
    work_item_suppressions: tuple[RoutineWorkItemSuppression, ...] = ()
    work_item_alarms: tuple[RoutineWorkItemAlarm, ...] = ()
    session_writes: tuple[UUID, ...] = ()


class _RoutineStore(Protocol):
    def register(
        self, tenant_id: UUID, revision: RoutineRevision, *, first_fire_at: datetime | None
    ) -> None: ...

    def scan(self, tenant_id: UUID) -> SchedulerScan: ...

    def tenant_ids(self) -> tuple[UUID, ...]: ...

    def complete_routine_work_item(
        self, actor: Actor, command: CompleteRoutineWorkItemCommand
    ) -> RoutineWorkItemReceipt | RecordProblem: ...

    def alarm_episodes(self, tenant_id: UUID) -> tuple[RoutineAlarmEpisode, ...]: ...


class _FixedOperationStore(Protocol):
    def start_synthetic(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command: SyntheticRunCommand,
        revision: RoutineRevision,
    ) -> SyntheticRunReceipt | RecordProblem: ...

    def claim_synthetic(self, worker_ref: str) -> FixedOperationAttempt | None: ...

    def complete_synthetic(
        self,
        attempt: FixedOperationAttempt,
        completion: FixedOperationCompletion,
    ) -> FixedOperationResult: ...

    def synthetic_run(self, tenant_id: UUID, run_id: UUID) -> SyntheticRun | None: ...


class FixedOperations:
    """Execute only the fixed synthetic operation through immutable receipts."""

    def __init__(self, store: _FixedOperationStore) -> None:
        self._store = store

    def start_synthetic(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command: SyntheticRunCommand,
        revision: RoutineRevision,
    ) -> SyntheticRunReceipt | RecordProblem:
        return self._store.start_synthetic(tenant_id, principal_id, command, revision)

    def claim_synthetic(self, worker_ref: str) -> FixedOperationAttempt | None:
        return self._store.claim_synthetic(worker_ref)

    def complete_synthetic(
        self,
        attempt: FixedOperationAttempt,
        completion: FixedOperationCompletion,
    ) -> FixedOperationResult:
        return self._store.complete_synthetic(attempt, completion)

    def synthetic_run(self, tenant_id: UUID, run_id: UUID) -> SyntheticRun | None:
        return self._store.synthetic_run(tenant_id, run_id)


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

    def complete_routine_work_item(
        self, actor: Actor, command: CompleteRoutineWorkItemCommand
    ) -> RoutineWorkItemReceipt | RecordProblem:
        return self._store.complete_routine_work_item(actor, command)

    def alarm_episodes(self, tenant_id: UUID) -> tuple[RoutineAlarmEpisode, ...]:
        """Project every append-only alarm episode this tenant has recorded."""

        return self._store.alarm_episodes(tenant_id)


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
    dream_dispatch: DreamDispatchSpec | None = None
    minute_marks: tuple[int, ...] = ()
    hour_marks: tuple[int, ...] | None = None
    routine_item: RoutineItemSpec | None = None
    activity_gate: ActivityGate | None = None

    def __post_init__(self) -> None:
        _validate_revision_identity(self)
        _validate_revision_limits(self)
        _validate_revision_schedule(self)

    def next_fire_after(self, instant: datetime) -> datetime:
        """Return the next unique UTC decision instant, including a visible DST gap."""

        _aware(instant)
        if self.schedule_kind is ScheduleKind.HOURLY:
            current = instant.astimezone(UTC)
            return current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        if self.schedule_kind is ScheduleKind.MINUTE_HOUR_SET:
            zone = ZoneInfo(self.timezone)
            local = instant.astimezone(zone).replace(second=0, microsecond=0)
            for minutes in range(1, 60 * 24 * 8):
                candidate = local + timedelta(minutes=minutes)
                if candidate.minute in self.minute_marks and (
                    self.hour_marks is None or candidate.hour in self.hour_marks
                ):
                    return candidate.astimezone(UTC)
            raise RuntimeError("minute-hour Routine has no resolvable fire in the bounded calendar")
        zone = ZoneInfo(self.timezone)
        local_date = instant.astimezone(zone).date()
        for days in range(370):
            candidate, _, _ = _wall_clock_decision(
                local_date + timedelta(days=days), self.local_time, zone
            )
            if candidate > instant:
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
    if revision.handler_kind not in _HANDLERS:
        raise ValueError("Routine handler is outside the authored fixed subset")
    if (revision.handler_kind == "dream_dispatch") != (revision.dream_dispatch is not None):
        raise ValueError("only a dream-dispatch Routine carries effect facts")
    if (revision.handler_kind == "routine_item") != (revision.routine_item is not None):
        raise ValueError("only a routine-item Routine carries Inbox work-item facts")


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
    if revision.schedule_kind is ScheduleKind.MINUTE_HOUR_SET:
        _validate_minute_hour_schedule(revision)
    elif revision.minute_marks or revision.hour_marks is not None:
        raise ValueError("only a minute-hour Routine carries minute and hour marks")
    try:
        ZoneInfo(revision.timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Routine timezone must be an installed IANA zone") from error


def _validate_minute_hour_schedule(revision: RoutineRevision) -> None:
    if revision.local_time is not None:
        raise ValueError("minute-hour Routine cannot carry a local civil time")
    _validate_marks(revision.minute_marks, maximum=_MAX_MINUTE_MARK, label="minute")
    if revision.hour_marks is not None:
        _validate_marks(revision.hour_marks, maximum=_MAX_HOUR_MARK, label="hour")


def _validate_marks(marks: tuple[int, ...], *, maximum: int, label: str) -> None:
    if (
        not marks
        or tuple(sorted(set(marks))) != marks
        or any(mark < 0 or mark > maximum for mark in marks)
    ):
        raise ValueError(f"{label} marks must be unique, ordered, and between 0 and {maximum}")


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
    zone = ZoneInfo(routine.timezone)
    local = scheduled_for.astimezone(zone)
    offset_decision = ScheduleOffsetDecision.EXACT
    local_civil_time = local.replace(tzinfo=None)
    offset = local.utcoffset()
    if routine.schedule_kind is ScheduleKind.DAILY:
        decision_at, offset, offset_decision = _wall_clock_decision(
            local.date(), routine.local_time, zone
        )
        if decision_at != scheduled_for.astimezone(UTC):
            raise ValueError("daily Routine instant does not match its wall-clock decision")
        if routine.local_time is None:
            raise RuntimeError("daily Routine local time disappeared")
        local_civil_time = datetime.combine(local.date(), routine.local_time)
    if offset is None and offset_decision is not ScheduleOffsetDecision.NONEXISTENT_LOCAL_TIME:
        raise RuntimeError("Routine local offset is unavailable")
    if offset_decision is ScheduleOffsetDecision.NONEXISTENT_LOCAL_TIME:
        outcome = OccurrenceOutcome.SKIPPED
    return OccurrencePlan(
        scheduled_for=scheduled_for.astimezone(UTC),
        local_civil_time=local_civil_time.isoformat(),
        utc_offset_seconds=int(offset.total_seconds()) if offset is not None else None,
        offset_decision=offset_decision,
        outcome=outcome,
    )


def _wall_clock_decision(
    day: date, at: time | None, zone: ZoneInfo
) -> tuple[datetime, timedelta | None, ScheduleOffsetDecision]:
    if at is None:
        raise RuntimeError("daily Routine local time disappeared")
    naive = datetime.combine(day, at)
    candidates: set[datetime] = set()
    for fold in (0, 1):
        utc = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc)
    if not candidates:
        proxy = naive.replace(tzinfo=zone, fold=0).astimezone(UTC)
        return proxy, None, ScheduleOffsetDecision.NONEXISTENT_LOCAL_TIME
    selected = min(candidates)
    local = selected.astimezone(zone)
    decision = (
        ScheduleOffsetDecision.EARLIER_OFFSET
        if len(candidates) > 1
        else ScheduleOffsetDecision.EXACT
    )
    return selected, local.utcoffset(), decision


def _aware(value: datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("Routine instants must be timezone-aware")
