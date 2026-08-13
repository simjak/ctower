"""Pure deterministic Request-maintenance proposal projection contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest

from ctower_kernel.projections.request_proposals import (
    ProposalReviewInput,
    ProposalSummaryInput,
    derive_request_maintenance_review,
    derive_request_maintenance_summary,
)

__all__: tuple[str, ...] = ()
REVIEW_LIMIT = 20
SUMMARY_WATERMARK = 67
PARTIAL_WATERMARK = 44


@pytest.mark.parametrize("row_count", (0, 1, 20, 21, 75))
def test_review_has_one_deterministic_fixed_limit_for_every_queue_size(row_count: int) -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    inputs = tuple(
        ProposalReviewInput(
            request_id=UUID(int=index + 1),
            proposal_id=UUID(int=1000 + index),
            goal_relevance="relevant",
            operator_decision_required=False,
            created_at=now,
        )
        for index in range(row_count)
    )

    review = derive_request_maintenance_review(reversed(inputs), watermark=42)

    assert len(review.rows) == min(row_count, REVIEW_LIMIT)
    assert tuple(row.request_id for row in review.rows) == tuple(
        UUID(int=index + 1) for index in range(min(row_count, REVIEW_LIMIT))
    )


def test_review_is_deterministic_and_fixed_at_twenty() -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    inputs = tuple(
        ProposalReviewInput(
            request_id=UUID(int=index + 1),
            proposal_id=UUID(int=100 + index),
            goal_relevance="relevant" if index % 2 else "unknown",
            operator_decision_required=index % 3 == 0,
            created_at=now,
        )
        for index in range(21)
    )

    first = derive_request_maintenance_review(inputs, watermark=42)
    second = derive_request_maintenance_review(tuple(reversed(inputs)), watermark=42)

    assert first == second
    assert len(first.rows) == REVIEW_LIMIT
    assert first.partial is True


def test_review_orders_approved_goal_operator_age_and_stable_identity_keys() -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    facts = (
        (4, "unknown", True),
        (3, "not-relevant", True),
        (2, "relevant", False),
        (5, "relevant", True),
        (1, "relevant", True),
    )
    inputs = tuple(
        ProposalReviewInput(
            request_id=UUID(int=identity),
            proposal_id=UUID(int=100 + identity),
            goal_relevance=relevance,
            operator_decision_required=required,
            created_at=now,
        )
        for identity, relevance, required in facts
    )

    review = derive_request_maintenance_review(inputs, watermark=55)

    assert tuple(row.request_id for row in review.rows) == tuple(
        UUID(int=value) for value in (1, 5, 2, 3, 4)
    )
    assert review.partial is True
    assert review.unanswered_sources == ("goal-relevance",)


def test_review_has_one_request_row_and_names_conflicting_duplicate_source_facts() -> None:
    now = datetime(2026, 8, 13, tzinfo=UTC)
    request_id = UUID(int=1)
    inputs = (
        ProposalReviewInput(
            request_id,
            UUID(int=200),
            "relevant",
            operator_decision_required=True,
            created_at=now,
        ),
        ProposalReviewInput(
            request_id,
            UUID(int=100),
            "relevant",
            operator_decision_required=False,
            created_at=now,
        ),
    )

    review = derive_request_maintenance_review(inputs, watermark=56)

    assert tuple(row.proposal_id for row in review.rows) == (UUID(int=100),)
    assert review.partial is True
    assert review.unanswered_sources == (f"request-review-conflict:{request_id}",)


def test_summary_is_counts_pointer_and_watermark_only() -> None:
    summary = derive_request_maintenance_summary(
        (
            ProposalSummaryInput("duplicate", "OPEN"),
            ProposalSummaryInput("duplicate", "CONFIRMED"),
            ProposalSummaryInput("keep", "REJECTED"),
        ),
        watermark=SUMMARY_WATERMARK,
    )

    payload = summary.response_payload()
    assert payload["by_kind"] == {
        "completed_but_open": 0,
        "duplicate": 2,
        "keep": 1,
        "kill": 0,
        "supersession": 0,
    }
    assert payload["by_state"] == {"CONFIRMED": 1, "OPEN": 1, "REJECTED": 1}
    assert payload["pointer"] == "/v1/request-maintenance/review"
    assert payload["watermark"] == SUMMARY_WATERMARK
    assert "rows" not in payload

    partial = derive_request_maintenance_summary(
        (ProposalSummaryInput("keep", "OPEN"),),
        watermark=PARTIAL_WATERMARK,
        unreached_scopes=("project:unanswered",),
    ).response_payload()
    assert set(cast(dict[str, object], partial["by_kind"]).values()) == {None}
    assert set(cast(dict[str, object], partial["by_state"]).values()) == {None}
    assert partial["watermark"] == PARTIAL_WATERMARK
