"""Small read-only Interface for the truthful disposable Board projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ctower_kernel.projections.project_delivery import (
    CtowerProjectCutoverHealth,
    ProjectDeliveryView,
)
from ctower_kernel.record import Actor, DurabilityHealth

__all__ = [
    "BoardCard",
    "BoardFacts",
    "BoardLane",
    "BoardQuery",
    "BoardView",
    "ControlHealth",
    "HealthContributor",
    "HealthContributorKey",
    "HealthDimension",
    "HealthStatus",
    "ProjectionHealth",
    "Projections",
    "derive_board_card",
]
_MAX_HEALTH_OWNER_LENGTH = 128
_MAX_HEALTH_REASON_LENGTH = 500


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


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STATE_UNKNOWN = "STATE_UNKNOWN"


class HealthContributorKey(StrEnum):
    DURABILITY = "durability"
    SCHEDULER = "scheduler"
    OUTBOX = "outbox"
    PROJECTION = "projection"
    BACKUP = "backup"
    ANCHOR = "anchor"
    OBJECT = "object"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True, slots=True)
class HealthContributor:
    key: HealthContributorKey
    status: HealthStatus
    watermark: int | None
    threshold_seconds: int
    observed_at: datetime
    owner: str
    reason: str

    def __post_init__(self) -> None:
        if self.watermark is not None and self.watermark < 0:
            raise ValueError("health watermark cannot be negative")
        if self.threshold_seconds < 0:
            raise ValueError("health threshold cannot be negative")
        if self.observed_at.tzinfo is None:
            raise ValueError("health observation must be timezone-aware")
        owner_valid = 1 <= len(self.owner) <= _MAX_HEALTH_OWNER_LENGTH
        reason_valid = 1 <= len(self.reason) <= _MAX_HEALTH_REASON_LENGTH
        if not owner_valid or not reason_valid:
            raise ValueError("health attribution is outside the authored contract")

    def response_payload(self) -> dict[str, object]:
        return {
            "key": self.key.value,
            "status": self.status.value,
            "watermark": self.watermark,
            "threshold_seconds": self.threshold_seconds,
            "observed_at": self.observed_at.isoformat(),
            "owner": self.owner,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class HealthDimension:
    status: HealthStatus
    contributors: tuple[HealthContributor, ...]

    def __post_init__(self) -> None:
        keys = tuple(item.key for item in self.contributors)
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("health dimension contributors must be nonempty and unique")

    def response_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "contributors": [item.response_payload() for item in self.contributors],
        }


@dataclass(frozen=True, slots=True)
class ControlHealth:
    status: HealthStatus
    observed_at: datetime
    availability: HealthDimension
    completeness: HealthDimension
    integrity: HealthDimension

    def __post_init__(self) -> None:
        contributors = (
            self.availability.contributors
            + self.completeness.contributors
            + self.integrity.contributors
        )
        keys = tuple(item.key for item in contributors)
        if len(keys) != len(set(keys)) or set(keys) != set(HealthContributorKey):
            raise ValueError("control health must attribute every contributor exactly once")

    def response_payload(self) -> dict[str, object]:
        return {
            "schema_id": "ctower.health/v1",
            "status": self.status.value,
            "observed_at": self.observed_at.isoformat(),
            "availability": self.availability.response_payload(),
            "completeness": self.completeness.response_payload(),
            "integrity": self.integrity.response_payload(),
        }


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

    def health(
        self, tenant_id: UUID, durability: DurabilityHealth, *, now: datetime
    ) -> ControlHealth: ...

    def cutover_health(self, actor: Actor) -> CtowerProjectCutoverHealth: ...

    def project_delivery(self, actor: Actor, project_key: str) -> ProjectDeliveryView | None: ...


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

    def health(self, actor: Actor, durability: DurabilityHealth, *, now: datetime) -> ControlHealth:
        return self._store.health(actor.tenant_id, durability, now=now)

    def cutover_health(self, actor: Actor) -> CtowerProjectCutoverHealth:
        """Read the latest append-only authority fact or the safe pre-cutover default."""

        return self._store.cutover_health(actor)

    def project_delivery(self, actor: Actor, project_key: str) -> ProjectDeliveryView | None:
        """Read stored compact rows without accepting a desired status."""

        return self._store.project_delivery(actor, project_key)


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
