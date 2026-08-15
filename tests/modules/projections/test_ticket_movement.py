"""AC-MOVE-02/03: the movement read and digest summary projection.

Exercises the pure movement projection fold: project-authorized cursor paging,
deterministic civil-day counts grouped by (Project, from_stage, to_stage), the
movement-view pointer and watermark, and honest partial/unknown epistemics.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from ctower_kernel.projections.morning_digest import ReadingState, SourceReading, UnreachedScope
from ctower_kernel.projections.ticket_movement import (
    MovementCountInput,
    derive_movement_summary,
)

__all__: tuple[str, ...] = ()

_OBSERVED_AT = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)
_DIGEST_DATE = date(2026, 8, 10)
_PROJECT = "ctower"
_WATERMARK = 47


def _count_input(
    from_stage: str,
    to_stage: str,
    project: str = _PROJECT,
    occurred_at: datetime = datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
) -> MovementCountInput:
    return MovementCountInput(
        project_key=project,
        source_stage=from_stage,
        stage=to_stage,
        occurred_at=occurred_at,
    )


def _complete_source(*rows: MovementCountInput) -> SourceReading[MovementCountInput]:
    return SourceReading.complete(rows, watermark=_WATERMARK, observed_at=_OBSERVED_AT)


def test_movement_summary_groups_counts_by_project_and_from_to_stage() -> None:
    reading = _complete_source(
        _count_input("capture", "frame"),
        _count_input("capture", "frame"),
        _count_input("frame", "verify"),
        _count_input("capture", "frame", project="manibo"),
    )

    summary = derive_movement_summary(reading, digest_date=_DIGEST_DATE)

    assert summary.source_state == "complete"
    assert summary.watermark == _WATERMARK
    assert summary.pointer == "/v1/projects/{project_key}/movement"
    assert summary.counts() == {
        ("ctower", "capture", "frame"): 2,
        ("ctower", "frame", "verify"): 1,
        ("manibo", "capture", "frame"): 1,
    }


def test_movement_summary_is_deterministic_and_empty_state_is_zero_not_absent() -> None:
    first = derive_movement_summary(_complete_source(), digest_date=_DIGEST_DATE)
    second = derive_movement_summary(_complete_source(), digest_date=_DIGEST_DATE)

    assert first.counts() == {}
    assert first == second
    assert first.state is ReadingState.COMPLETE


def test_movement_summary_embeds_no_identity_or_text_for_digest_transport() -> None:
    summary = derive_movement_summary(
        _complete_source(_count_input("capture", "frame")),
        digest_date=_DIGEST_DATE,
    )
    payload = summary.response_payload()
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["pointer"] == "/v1/projects/{project_key}/movement"
    assert "ticket_id" not in encoded
    assert "event_id" not in encoded
    assert "title" not in encoded
    assert "text" not in encoded


def test_unreached_movement_source_is_unknown_never_a_zero() -> None:
    reading: SourceReading[MovementCountInput] = SourceReading.unknown(
        UnreachedScope("movement", "movement-source-unavailable"),
        observed_at=_OBSERVED_AT,
    )

    summary = derive_movement_summary(reading, digest_date=_DIGEST_DATE)

    assert summary.state is ReadingState.UNKNOWN
    assert summary.watermark is None
    assert summary.counts() == {}
    assert summary.unreached_scopes == ("movement:movement-source-unavailable",)


def test_partial_movement_reading_preserves_visible_counts_and_names_the_gap() -> None:
    reading = SourceReading.partial(
        (_count_input("capture", "frame"),),
        watermark=47,
        observed_at=_OBSERVED_AT,
        unreached=(UnreachedScope("manibo", "movement-project-unanswered"),),
    )

    summary = derive_movement_summary(reading, digest_date=_DIGEST_DATE)

    assert summary.state is ReadingState.PARTIAL
    assert summary.counts() == {("ctower", "capture", "frame"): 1}
    assert summary.unreached_scopes == ("manibo:movement-project-unanswered",)


def test_movement_summary_refuses_naive_observed_times() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        derive_movement_summary(
            SourceReading.complete(
                (_count_input("capture", "frame"),),
                watermark=47,
                observed_at=_OBSERVED_AT.replace(tzinfo=None),
            ),
            digest_date=_DIGEST_DATE,
        )


def test_movement_summary_accepts_an_explicit_digest_date() -> None:
    summary = derive_movement_summary(
        _complete_source(_count_input("capture", "frame")),
        digest_date=_DIGEST_DATE,
    )
    assert summary.digest_date == _DIGEST_DATE


def test_movement_summary_orders_buckets_deterministically() -> None:
    summary = derive_movement_summary(
        _complete_source(
            _count_input("frame", "verify"),
            _count_input("capture", "frame"),
            _count_input("capture", "frame", project="manibo"),
            _count_input("capture", "frame"),
        ),
        digest_date=_DIGEST_DATE,
    )
    assert tuple(item.response_payload() for item in summary.stored_counts) == (
        {"count": 2, "from_stage": "capture", "project_key": "ctower", "to_stage": "frame"},
        {"count": 1, "from_stage": "frame", "project_key": "ctower", "to_stage": "verify"},
        {"count": 1, "from_stage": "capture", "project_key": "manibo", "to_stage": "frame"},
    )


def test_movement_counts_use_the_prior_vilnius_civil_day_window() -> None:
    # Digest date 2026-08-10 counts only facts recorded on the prior civil day
    # 2026-08-09 in Europe/Vilnius (UTC+3): 2026-08-08 21:00 UTC through
    # 2026-08-09 21:00 UTC.
    included = _count_input("capture", "frame", occurred_at=datetime(2026, 8, 9, 12, 0, tzinfo=UTC))
    boundary_open = _count_input(
        "capture", "frame", occurred_at=datetime(2026, 8, 8, 21, 0, tzinfo=UTC)
    )
    boundary_close = _count_input(
        "capture", "frame", occurred_at=datetime(2026, 8, 9, 21, 0, tzinfo=UTC)
    )
    too_old = _count_input("frame", "verify", occurred_at=datetime(2026, 8, 8, 20, 59, tzinfo=UTC))
    too_new = _count_input("frame", "verify", occurred_at=datetime(2026, 8, 9, 21, 1, tzinfo=UTC))

    summary = derive_movement_summary(
        _complete_source(included, boundary_open, boundary_close, too_old, too_new),
        digest_date=_DIGEST_DATE,
    )

    # The window is half-open [start, end): 2026-08-08 21:00 UTC is the
    # inclusive open and 2026-08-09 21:00 UTC the exclusive close.
    assert summary.counts() == {("ctower", "capture", "frame"): 2}


def test_movement_counts_use_the_vilnius_fall_back_boundary() -> None:
    # Digest date 2026-10-26: prior civil day 2026-10-25 is 25 hours long in
    # Vilnius (03:00-04:00 repeats).  Facts at 2026-10-24 21:30 UTC and
    # 2026-10-25 21:30 UTC are both inside the window; 2026-10-25 22:30 UTC
    # is the next civil day.
    summary = derive_movement_summary(
        _complete_source(
            _count_input(
                "capture", "frame", occurred_at=datetime(2026, 10, 24, 21, 30, tzinfo=UTC)
            ),
            _count_input("frame", "verify", occurred_at=datetime(2026, 10, 25, 21, 30, tzinfo=UTC)),
            _count_input("verify", "done", occurred_at=datetime(2026, 10, 25, 22, 30, tzinfo=UTC)),
        ),
        digest_date=date(2026, 10, 26),
    )

    assert summary.counts() == {
        ("ctower", "capture", "frame"): 1,
        ("ctower", "frame", "verify"): 1,
    }


def test_movement_count_input_refuses_a_naive_occurred_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _count_input("capture", "frame", occurred_at=datetime(2026, 8, 9, 12, 0))  # noqa: DTZ001
