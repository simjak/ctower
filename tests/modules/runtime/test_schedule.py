"""Deterministic Routine scheduling through the public Runtime Interface."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time
from pathlib import Path

import pytest

from ctower_api.control_worker import load_routine_revisions
from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    OccurrenceOutcome,
    RoutineRevision,
    ScheduleKind,
)

ROOT = Path(__file__).parents[3]


def test_wall_clock_once_records_dst_gap_and_uses_earlier_repeated_offset() -> None:
    routine = _daily("America/New_York", time(2, 30))

    after_gap_eve = datetime(2026, 3, 7, 7, 30, tzinfo=UTC)
    after_repeat_eve = datetime(2026, 10, 31, 6, 30, tzinfo=UTC)

    gap = routine.next_fire_after(after_gap_eve)
    assert gap == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
    gap_plan = routine.plan_due((gap,))
    assert gap_plan[0].local_civil_time == "2026-03-08T02:30:00"
    assert gap_plan[0].utc_offset_seconds is None
    assert gap_plan[0].offset_decision == "nonexistent_local_time"
    assert gap_plan[0].outcome is OccurrenceOutcome.SKIPPED
    repeated = _daily("America/New_York", time(1, 30)).next_fire_after(after_repeat_eve)
    assert repeated == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert repeated.utcoffset() == UTC.utcoffset(repeated)
    repeated_plan = _daily("America/New_York", time(1, 30)).plan_due((repeated,))
    assert repeated_plan[0].offset_decision == "earlier_offset"


def test_occurrence_outcomes_include_typed_refusal() -> None:
    assert OccurrenceOutcome.REFUSED.value == "refused"


def test_catch_up_is_bounded_and_keeps_the_latest_due_fire() -> None:
    routine = _daily("UTC", time(1, 0), catch_up=CatchUpPolicy.ENQUEUE_MISSED_WITH_CAP)
    due = (
        datetime(2026, 7, 19, 1, tzinfo=UTC),
        datetime(2026, 7, 20, 1, tzinfo=UTC),
        datetime(2026, 7, 21, 1, tzinfo=UTC),
    )

    planned = routine.plan_due(due)

    assert [item.scheduled_for for item in planned] == list(due)
    assert [item.outcome for item in planned] == [
        OccurrenceOutcome.SKIPPED,
        OccurrenceOutcome.SKIPPED,
        OccurrenceOutcome.QUEUED,
    ]


def test_serialize_one_pending_never_plans_a_second_pending_job() -> None:
    routine = _daily(
        "UTC",
        time(1, 0),
        concurrency=ConcurrencyPolicy.SERIALIZE_ONE_PENDING,
        catch_up=CatchUpPolicy.COALESCE_LATEST,
    )
    due = (datetime(2026, 7, 22, 1, tzinfo=UTC),)

    first = routine.plan_due(due, active_jobs=1, pending_jobs=0)
    duplicate = routine.plan_due(due, active_jobs=1, pending_jobs=1)

    assert first[0].outcome is OccurrenceOutcome.QUEUED
    assert duplicate[0].outcome is OccurrenceOutcome.COALESCED


def test_hourly_empty_and_invalid_due_inputs_are_explicit() -> None:
    routine = replace(
        _daily("UTC", time(1, 0)),
        schedule_kind=ScheduleKind.HOURLY,
        local_time=None,
        concurrency=ConcurrencyPolicy.SKIP_IF_ACTIVE,
    )
    instant = datetime(2026, 7, 22, 1, 20, 30, tzinfo=UTC)

    assert routine.next_fire_after(instant) == datetime(2026, 7, 22, 2, tzinfo=UTC)
    assert routine.plan_due(()) == ()
    skipped = routine.plan_due((instant,), active_jobs=1)
    assert skipped[0].outcome is OccurrenceOutcome.SKIPPED
    naive = instant.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        routine.next_fire_after(naive)
    with pytest.raises(ValueError, match="cannot be negative"):
        routine.plan_due((instant,), active_jobs=-1)
    with pytest.raises(ValueError, match="unique and ordered"):
        routine.plan_due((instant, instant))


def test_minute_hour_set_fires_at_each_authored_utc_mark() -> None:
    every_hour = replace(
        _daily("UTC", time(1, 0)),
        schedule_kind=ScheduleKind.MINUTE_HOUR_SET,
        local_time=None,
        minute_marks=(14, 34, 54),
    )
    selected_hours = replace(every_hour, minute_marks=(23,), hour_marks=(2, 8, 14, 20))

    assert every_hour.next_fire_after(datetime(2026, 8, 10, 9, 14, tzinfo=UTC)) == datetime(
        2026, 8, 10, 9, 34, tzinfo=UTC
    )
    assert every_hour.next_fire_after(datetime(2026, 8, 10, 9, 54, tzinfo=UTC)) == datetime(
        2026, 8, 10, 10, 14, tzinfo=UTC
    )
    assert selected_hours.next_fire_after(datetime(2026, 8, 10, 8, 23, tzinfo=UTC)) == datetime(
        2026, 8, 10, 14, 23, tzinfo=UTC
    )


def test_loaded_hour_specific_beats_preserve_vilnius_wall_clock_across_dst() -> None:
    beats = {
        revision.routine_ref: revision
        for revision in load_routine_revisions(ROOT / "packs")
        if revision.routine_ref in {"ctower.beat.digest@1", "ctower.beat.sprint@1"}
    }
    digest = beats["ctower.beat.digest@1"]
    sprint = beats["ctower.beat.sprint@1"]

    def next_four(after: datetime) -> tuple[datetime, ...]:
        fires: list[datetime] = []
        for _ in range(4):
            after = sprint.next_fire_after(after)
            fires.append(after)
        return tuple(fires)

    assert digest.timezone == sprint.timezone == "Europe/Vilnius"
    assert digest.next_fire_after(datetime(2026, 8, 10, tzinfo=UTC)) == datetime(
        2026, 8, 10, 4, 12, tzinfo=UTC
    )
    assert digest.next_fire_after(datetime(2026, 12, 10, tzinfo=UTC)) == datetime(
        2026, 12, 10, 5, 12, tzinfo=UTC
    )
    assert next_four(datetime(2026, 8, 10, 20, tzinfo=UTC)) == (
        datetime(2026, 8, 10, 23, 23, tzinfo=UTC),
        datetime(2026, 8, 11, 5, 23, tzinfo=UTC),
        datetime(2026, 8, 11, 11, 23, tzinfo=UTC),
        datetime(2026, 8, 11, 17, 23, tzinfo=UTC),
    )
    assert next_four(datetime(2026, 12, 10, 20, tzinfo=UTC)) == (
        datetime(2026, 12, 11, 0, 23, tzinfo=UTC),
        datetime(2026, 12, 11, 6, 23, tzinfo=UTC),
        datetime(2026, 12, 11, 12, 23, tzinfo=UTC),
        datetime(2026, 12, 11, 18, 23, tzinfo=UTC),
    )


def test_minute_hour_set_rejects_invalid_or_missing_marks() -> None:
    base = _daily("UTC", time(1, 0))
    with pytest.raises(ValueError, match="minute marks"):
        replace(base, schedule_kind=ScheduleKind.MINUTE_HOUR_SET, local_time=None)
    with pytest.raises(ValueError, match="minute marks"):
        replace(
            base,
            schedule_kind=ScheduleKind.MINUTE_HOUR_SET,
            local_time=None,
            minute_marks=(60,),
        )
    with pytest.raises(ValueError, match="hour marks"):
        replace(
            base,
            schedule_kind=ScheduleKind.MINUTE_HOUR_SET,
            local_time=None,
            minute_marks=(12,),
            hour_marks=(24,),
        )


def test_routine_revision_rejects_invalid_authored_contract_values() -> None:
    routine = _daily("UTC", time(1, 0))

    with pytest.raises(ValueError, match="reference"):
        replace(routine, routine_ref="unversioned")
    with pytest.raises(ValueError, match="revision digest"):
        replace(routine, revision_digest="not-a-digest")
    with pytest.raises(ValueError, match="components"):
        replace(routine, component_digests=())
    with pytest.raises(ValueError, match="authored fixed subset"):
        replace(routine, handler_kind="arbitrary_effect")
    with pytest.raises(ValueError, match="catch-up cap"):
        replace(routine, catch_up_cap=0)
    with pytest.raises(ValueError, match="timeout"):
        replace(routine, timeout_seconds=0)
    with pytest.raises(ValueError, match="local civil time"):
        replace(routine, local_time=time(1, 0, tzinfo=UTC))
    with pytest.raises(ValueError, match="daily Routine"):
        replace(routine, local_time=None)
    with pytest.raises(ValueError, match="IANA zone"):
        replace(routine, timezone="Not/A_Real_Zone")


def _daily(
    zone: str,
    at: time,
    *,
    concurrency: ConcurrencyPolicy = ConcurrencyPolicy.COALESCE_IF_ACTIVE,
    catch_up: CatchUpPolicy = CatchUpPolicy.SKIP_MISSED,
) -> RoutineRevision:
    return RoutineRevision(
        routine_ref="ctower.test.schedule@1",
        revision_digest="sha256:" + "1" * 64,
        schedule_kind=ScheduleKind.DAILY,
        timezone=zone,
        local_time=at,
        concurrency=concurrency,
        catch_up=catch_up,
        catch_up_cap=1,
        handler_kind="synthetic_four_stage",
        timeout_seconds=60,
        component_digests=("sha256:" + "2" * 64,),
    )
