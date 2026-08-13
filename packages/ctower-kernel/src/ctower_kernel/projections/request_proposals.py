"""Pure deterministic folds for Request-maintenance proposal review and summary."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

__all__ = [
    "ProposalReviewInput",
    "ProposalSummaryInput",
    "RequestMaintenanceProposalSummary",
    "RequestMaintenanceReview",
    "RequestMaintenanceReviewRow",
    "derive_request_maintenance_review",
    "derive_request_maintenance_summary",
]

_KINDS = ("duplicate", "completed-but-open", "supersession", "kill", "keep")
_STATES = ("OPEN", "CONFIRMED", "REJECTED")
_REVIEW_LIMIT = 20
_RELEVANCE_RANK = {"relevant": 0, "not-relevant": 1, "unknown": 2}


@dataclass(frozen=True, slots=True)
class ProposalReviewInput:
    """One strictly sourced proposal-to-Request review relation."""

    request_id: UUID
    proposal_id: UUID
    goal_relevance: str
    operator_decision_required: bool
    created_at: datetime

    def __post_init__(self) -> None:
        if self.goal_relevance not in _RELEVANCE_RANK:
            raise ValueError("proposal Goal relevance is outside the typed source contract")
        if not isinstance(self.request_id, UUID) or not isinstance(self.proposal_id, UUID):
            raise TypeError("proposal review identities must be UUIDs")
        if self.created_at.tzinfo is None:
            raise ValueError("proposal review timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class RequestMaintenanceReviewRow:
    request_id: UUID
    proposal_id: UUID
    goal_relevance: str
    operator_decision_required: bool
    created_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "created_at": self.created_at.isoformat(),
            "goal_relevance": self.goal_relevance,
            "operator_decision_required": self.operator_decision_required,
            "proposal_id": str(self.proposal_id),
            "request_id": str(self.request_id),
        }


@dataclass(frozen=True, slots=True)
class RequestMaintenanceReview:
    rows: tuple[RequestMaintenanceReviewRow, ...]
    watermark: int
    partial: bool
    unanswered_sources: tuple[str, ...]
    observed_at: datetime
    pointer: str = "/v1/request-maintenance/review"

    def response_payload(self) -> dict[str, object]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "partial": self.partial,
            "pointer": self.pointer,
            "rows": [row.response_payload() for row in self.rows],
            "unanswered_sources": list(self.unanswered_sources),
            "watermark": self.watermark,
        }


@dataclass(frozen=True, slots=True)
class ProposalSummaryInput:
    kind: str
    state: str

    def __post_init__(self) -> None:
        if self.kind not in _KINDS or self.state not in _STATES:
            raise ValueError("proposal summary input is outside the closed vocabulary")


@dataclass(frozen=True, slots=True)
class RequestMaintenanceProposalSummary:
    by_kind: tuple[tuple[str, int | None], ...]
    by_state: tuple[tuple[str, int | None], ...]
    watermark: int | None
    source_state: str
    unreached_scopes: tuple[str, ...]
    pointer: str = "/v1/request-maintenance/review"

    def response_payload(self) -> dict[str, object]:
        by_kind = {
            ("completed_but_open" if key == "completed-but-open" else key): value
            for key, value in self.by_kind
        }
        return {
            "by_kind": by_kind,
            "by_state": dict(self.by_state),
            "pointer": self.pointer,
            "source_state": self.source_state,
            "unreached_scopes": list(self.unreached_scopes),
            "watermark": self.watermark,
        }


def derive_request_maintenance_review(
    inputs: Iterable[ProposalReviewInput],
    *,
    watermark: int,
    observed_at: datetime | None = None,
    unanswered_sources: tuple[str, ...] = (),
) -> RequestMaintenanceReview:
    """Order one top-20 view without similarity, scores, or caller relevance flags."""

    deduplicated, conflicts = _deduplicated_inputs(inputs)
    ordered = sorted(
        deduplicated,
        key=lambda item: (
            _RELEVANCE_RANK[item.goal_relevance],
            not item.operator_decision_required,
            item.created_at,
            item.request_id,
        ),
    )
    rows = tuple(
        RequestMaintenanceReviewRow(
            item.request_id,
            item.proposal_id,
            item.goal_relevance,
            item.operator_decision_required,
            item.created_at,
        )
        for item in ordered[:_REVIEW_LIMIT]
    )
    unknown = any(item.goal_relevance == "unknown" for item in ordered)
    unanswered = tuple(
        sorted(
            set(unanswered_sources) | set(conflicts) | ({"goal-relevance"} if unknown else set())
        )
    )
    derived_observed_at = observed_at or max(
        (item.created_at for item in ordered), default=datetime(1970, 1, 1, tzinfo=UTC)
    )
    return RequestMaintenanceReview(
        rows,
        watermark,
        bool(unanswered),
        unanswered,
        derived_observed_at,
    )


def _deduplicated_inputs(
    inputs: Iterable[ProposalReviewInput],
) -> tuple[tuple[ProposalReviewInput, ...], tuple[str, ...]]:
    by_request: dict[UUID, ProposalReviewInput] = {}
    conflicts: set[str] = set()
    for item in inputs:
        existing = by_request.get(item.request_id)
        if existing is not None and (
            existing.goal_relevance,
            existing.operator_decision_required,
            existing.created_at,
        ) != (
            item.goal_relevance,
            item.operator_decision_required,
            item.created_at,
        ):
            conflicts.add(f"request-review-conflict:{item.request_id}")
        if existing is None or item.proposal_id < existing.proposal_id:
            by_request[item.request_id] = item
    return tuple(by_request.values()), tuple(conflicts)


def derive_request_maintenance_summary(
    inputs: Iterable[ProposalSummaryInput],
    *,
    watermark: int,
    unreached_scopes: tuple[str, ...] = (),
) -> RequestMaintenanceProposalSummary:
    """Return only counts, one pointer, and source completeness for digest use."""

    materialized = tuple(inputs)
    complete = not unreached_scopes
    kinds = Counter(item.kind for item in materialized)
    states = Counter(item.state for item in materialized)
    source_state = "partial" if unreached_scopes else "complete"
    return RequestMaintenanceProposalSummary(
        tuple((kind, kinds[kind] if complete else None) for kind in _KINDS),
        tuple((state, states[state] if complete else None) for state in _STATES),
        watermark,
        source_state,
        tuple(sorted(set(unreached_scopes))),
    )
