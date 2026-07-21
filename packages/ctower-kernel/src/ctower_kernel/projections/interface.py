"""Small read-only Interface for the truthful disposable Board projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ctower_kernel.record import Actor

__all__ = [
    "BoardCard",
    "BoardFacts",
    "BoardLane",
    "BoardQuery",
    "BoardView",
    "ProjectionHealth",
    "Projections",
    "derive_board_card",
]


class BoardLane(StrEnum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class ProjectionHealth(StrEnum):
    CURRENT = "CURRENT"
    STATE_UNKNOWN = "STATE_UNKNOWN"


@dataclass(frozen=True, slots=True)
class BoardFacts:
    """Minimal authoritative facts consumed by the versioned fold."""

    ticket_id: UUID
    title: str
    priority: str
    lifecycle_state: str
    admitted: bool
    workflow_active: bool
    stage_key: str | None
    activity_class: str | None
    custodian_id: UUID
    assignee_id: UUID | None
    blocker_reason: str | None
    blocker_opened_at: datetime | None
    risk: str | None
    delivery_facts: tuple[str, ...]
    version: int


@dataclass(frozen=True, slots=True)
class BoardCard:
    ticket_id: UUID
    title: str
    lane: BoardLane
    underlying_lane: BoardLane | None
    priority: str
    stage_key: str | None
    activity_class: str | None
    custodian_id: UUID
    assignee_id: UUID | None
    blocker_reason: str | None
    blocker_opened_at: datetime | None
    risk: str | None
    delivery_facts: tuple[str, ...]
    version: int

    def response_payload(self) -> dict[str, object]:
        return {
            "activity_class": self.activity_class,
            "assignee_id": str(self.assignee_id) if self.assignee_id else None,
            "blocker_opened_at": (
                self.blocker_opened_at.isoformat() if self.blocker_opened_at else None
            ),
            "blocker_reason": self.blocker_reason,
            "custodian_id": str(self.custodian_id),
            "delivery_facts": list(self.delivery_facts),
            "lane": self.lane.value,
            "priority": self.priority,
            "risk": self.risk,
            "stage_key": self.stage_key,
            "stage_label": self.stage_key,
            "ticket_id": str(self.ticket_id),
            "title": self.title,
            "underlying_lane": (self.underlying_lane.value if self.underlying_lane else None),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class BoardQuery:
    lane: BoardLane | None = None
    priority: str | None = None
    stage_key: str | None = None
    custodian_id: UUID | None = None
    assignee_id: UUID | None = None
    risk: str | None = None


@dataclass(frozen=True, slots=True)
class BoardView:
    cards: tuple[BoardCard, ...]
    health: ProjectionHealth
    source_watermark: int
    projection_watermark: int

    def response_payload(self) -> dict[str, object]:
        return {
            "cards": [card.response_payload() for card in self.cards],
            "health": self.health.value,
            "projection_watermark": self.projection_watermark,
            "source_watermark": self.source_watermark,
        }


class _ProjectionStore(Protocol):
    def catch_up(self, tenant_id: UUID, through_watermark: int | None = None) -> BoardView: ...

    def board(self, actor: Actor, query: BoardQuery) -> BoardView: ...

    def rebuild(self, tenant_id: UUID) -> BoardView: ...


class Projections:
    """Expose catch-up, read, and deterministic rebuild without mutation commands."""

    def __init__(self, store: _ProjectionStore) -> None:
        self._store = store

    def catch_up(self, tenant_id: UUID, through_watermark: int | None = None) -> BoardView:
        return self._store.catch_up(tenant_id, through_watermark)

    def board(self, actor: Actor, query: BoardQuery) -> BoardView:
        return self._store.board(actor, query)

    def rebuild(self, tenant_id: UUID) -> BoardView:
        return self._store.rebuild(tenant_id)


def derive_board_card(facts: BoardFacts) -> BoardCard:
    """Fold orthogonal facts using the exact six-lane precedence."""

    lane = _underlying_lane(facts)
    underlying: BoardLane | None = None
    if facts.lifecycle_state in {"resolved", "closed"}:
        lane = BoardLane.COMPLETE
    elif facts.blocker_reason is not None:
        underlying = lane
        lane = BoardLane.BLOCKED
    return BoardCard(
        ticket_id=facts.ticket_id,
        title=facts.title,
        lane=lane,
        underlying_lane=underlying,
        priority=facts.priority,
        stage_key=facts.stage_key,
        activity_class=facts.activity_class,
        custodian_id=facts.custodian_id,
        assignee_id=facts.assignee_id,
        blocker_reason=facts.blocker_reason,
        blocker_opened_at=facts.blocker_opened_at,
        risk=facts.risk,
        delivery_facts=facts.delivery_facts,
        version=facts.version,
    )


def _underlying_lane(facts: BoardFacts) -> BoardLane:
    if not facts.admitted:
        return BoardLane.BACKLOG
    if not facts.workflow_active:
        return BoardLane.READY
    if facts.activity_class == "verification":
        return BoardLane.IN_REVIEW
    return BoardLane.IN_PROGRESS
