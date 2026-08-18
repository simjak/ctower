"""AC-RTN-01/02: typed gate model, evaluation semantics, and replay identity."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from ctower_kernel.runtime import (
    CatchUpPolicy,
    ConcurrencyPolicy,
    RoutineRevision,
    ScheduleKind,
)
from ctower_kernel.runtime.gates import (
    ActivityGate,
    GateDecision,
    GateOutcome,
    evaluate_gate,
)
from ctower_kernel.runtime.items import RoutineItemSpec

__all__: tuple[str, ...] = ()

_EXPECTED_BUSY_TICKETS = 2


def _revision(gate: ActivityGate | None) -> RoutineRevision:
    return RoutineRevision(
        routine_ref="mc-cron.capacity-sentinel@1",
        revision_digest="sha256:" + "ab" * 32,
        schedule_kind=ScheduleKind.MINUTE_HOUR_SET,
        timezone="UTC",
        local_time=None,
        concurrency=ConcurrencyPolicy.ALWAYS_ENQUEUE_BOUNDED,
        catch_up=CatchUpPolicy.SKIP_MISSED,
        catch_up_cap=1,
        timeout_seconds=600,
        handler_kind="routine_item",
        component_digests=("sha256:" + "cd" * 32,),
        minute_marks=(0, 10, 20, 30, 40, 50),
        hour_marks=None,
        routine_item=RoutineItemSpec(
            item_key="capacity-sentinel",
            knowledge_ref="mc-cron.capacity-sentinel",
            owner_seat="ctower-commander",
            escalation_seat="ctower-commander",
        ),
        activity_gate=gate,
    )


def test_gate_set_is_closed_and_unknown_kind_refuses() -> None:
    with pytest.raises(ValueError, match="closed gate set"):
        ActivityGate(kind="sql_expression")
    with pytest.raises(ValueError, match="closed gate set"):
        ActivityGate(kind="threshold_breach", threshold=1)
    ActivityGate(kind="always")
    ActivityGate(kind="new_movement_since_watermark", source="events")
    ActivityGate(kind="open_tickets_above", threshold=0)


def test_gate_scope_is_typed_and_foreign_project_refuses() -> None:
    with pytest.raises(ValueError, match="project key"):
        ActivityGate(kind="open_tickets_above", threshold=0, project_key="Not A Key!")
    with pytest.raises(ValueError, match="source"):
        ActivityGate(kind="new_movement_since_watermark", source="webhook")
    with pytest.raises(ValueError, match="threshold"):
        ActivityGate(kind="open_tickets_above", threshold=-1)


def test_revision_carries_its_gate_and_none_means_v3_semantics() -> None:
    gated = _revision(ActivityGate(kind="always"))
    assert gated.activity_gate is not None and gated.activity_gate.kind == "always"
    legacy = _revision(None)
    assert legacy.activity_gate is None


def test_evaluation_fires_only_on_schedule_and_gate_true() -> None:
    always = ActivityGate(kind="always")
    decision = evaluate_gate(
        always,
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        due=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        observed=0,
        watermark_position=None,
    )
    assert decision.outcome is GateOutcome.FIRED
    assert decision.watermark_kind == "none"

    sentinel = ActivityGate(kind="open_tickets_above", threshold=0)
    quiet = evaluate_gate(
        sentinel,
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        due=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        observed=0,
        watermark_position=None,
    )
    assert quiet.outcome is GateOutcome.SKIPPED
    assert quiet.watermark_kind == "tickets.nonterminal"

    busy = evaluate_gate(
        sentinel,
        now=datetime(2026, 8, 15, 12, 10, tzinfo=UTC),
        due=datetime(2026, 8, 15, 12, 10, tzinfo=UTC),
        observed=_EXPECTED_BUSY_TICKETS,
        watermark_position=None,
    )
    assert busy.outcome is GateOutcome.FIRED
    assert busy.observed_count == _EXPECTED_BUSY_TICKETS


def test_movement_gate_stands_on_a_named_watermark_and_replays_zero() -> None:
    movement = ActivityGate(kind="new_movement_since_watermark", source="events")
    watermark = datetime(2026, 8, 15, 11, 56, tzinfo=UTC)
    quiet = evaluate_gate(
        movement,
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        due=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        observed=0,
        watermark_position=watermark,
    )
    assert quiet.outcome is GateOutcome.SKIPPED
    assert quiet.watermark_kind == "events.server_time"
    assert quiet.watermark_position == watermark

    moved = evaluate_gate(
        movement,
        now=datetime(2026, 8, 15, 12, 4, tzinfo=UTC),
        due=datetime(2026, 8, 15, 12, 4, tzinfo=UTC),
        observed=1,
        watermark_position=datetime(2026, 8, 15, 11, 56, tzinfo=UTC),
    )
    assert moved.outcome is GateOutcome.FIRED

    baseline = evaluate_gate(
        movement,
        now=datetime(2026, 8, 15, 12, 4, tzinfo=UTC),
        due=datetime(2026, 8, 15, 12, 4, tzinfo=UTC),
        observed=1,
        watermark_position=None,
    )
    assert baseline.outcome is GateOutcome.FIRED, "first evaluation establishes the baseline"


def test_failed_read_yields_typed_degraded_never_clean_fire() -> None:
    movement = ActivityGate(kind="new_movement_since_watermark", source="events")
    degraded = evaluate_gate(
        movement,
        now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        due=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        observed=None,
        watermark_position=cast(datetime, object()),
    )
    assert degraded.outcome is GateOutcome.DEGRADED
    assert degraded.detail
    assert degraded.watermark_kind == "events.server_time"


def test_decision_fact_identity_is_deterministic_for_exact_replay() -> None:
    scheduled_for = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    first = GateDecision.fact_identity(scheduled_for, b"tenant", b"revision")
    second = GateDecision.fact_identity(scheduled_for, b"tenant", b"revision")
    other = GateDecision.fact_identity(scheduled_for, b"tenant", b"different")
    assert first == second != other
