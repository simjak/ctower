"""Deterministic Routine scheduling through the public Runtime Interface."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, time

import pytest

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    OccurrenceOutcome,
    RoutineRevision,
    ScheduleKind,
)


def test_wall_clock_once_skips_dst_gap_and_uses_earlier_repeated_offset() -> None:
    routine = _daily("America/New_York", time(2, 30))

    after_gap_eve = datetime(2026, 3, 7, 7, 30, tzinfo=UTC)
    after_repeat_eve = datetime(2026, 10, 31, 6, 30, tzinfo=UTC)

    assert routine.next_fire_after(after_gap_eve) == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
    repeated = _daily("America/New_York", time(1, 30)).next_fire_after(after_repeat_eve)
    assert repeated == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert repeated.utcoffset() == UTC.utcoffset(repeated)


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


def test_routine_revision_rejects_invalid_authored_contract_values() -> None:
    routine = _daily("UTC", time(1, 0))

    with pytest.raises(ValueError, match="reference"):
        replace(routine, routine_ref="unversioned")
    with pytest.raises(ValueError, match="revision digest"):
        replace(routine, revision_digest="not-a-digest")
    with pytest.raises(ValueError, match="components"):
        replace(routine, component_digests=())
    with pytest.raises(ValueError, match="fixed I1 subset"):
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
