"""Small read-only Interface for the truthful disposable Board projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ctower_kernel.projections.inbox import InboxReadState as _InboxReadState
from ctower_kernel.projections.project_delivery import (
    CtowerProjectCutoverHealth,
    DeliverySurfaceDeclaration,
    ProjectDeliveryView,
)
from ctower_kernel.record import Actor, DurabilityHealth

__all__ = [
    "AppliedLabel",
    "BoardCard",
    "BoardDeliverySurfaceAvailability",
    "BoardDeliverySurfaceState",
    "BoardFacts",
    "BoardLane",
    "BoardQuery",
    "BoardView",
    "ChangeReference",
    "ControlHealth",
    "HealthContributor",
    "HealthContributorKey",
    "HealthDimension",
    "HealthStatus",
    "HumanWaiting",
    "HumanWaitingState",
    "InboxMessage",
    "InboxThread",
    "InboxThreadList",
    "InboxThreadSummary",
    "ProjectionHealth",
    "Projections",
    "TenantDisplayIdentity",
    "TenantDisplayState",
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
    project_key: str
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


class TenantDisplayState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TenantDisplayIdentity:
    """INV-66: the tenant's recorded display fact, or an explicit unknown."""

    state: TenantDisplayState
    display_name: str | None = None
    missing_source: str | None = None

    def __post_init__(self) -> None:
        if self.state is TenantDisplayState.KNOWN and not self.display_name:
            raise ValueError("a known tenant display identity must carry a display name")
        if self.state is TenantDisplayState.UNKNOWN and not self.missing_source:
            raise ValueError("an unknown tenant display identity must name its missing source")

    def response_payload(self) -> dict[str, object]:
        if self.state is TenantDisplayState.KNOWN:
            return {"state": "known", "display_name": self.display_name}
        return {"state": "unknown", "missing_source": self.missing_source}


@dataclass(frozen=True, slots=True)
class ChangeReference:
    """INV-66: a linked Change fact, exposed exactly as recorded."""

    repository: str
    change_identity: str
    reference: str
    recorded_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "change_identity": self.change_identity,
            "reference": self.reference,
            "recorded_at": self.recorded_at.isoformat(),
            "repository": self.repository,
        }


@dataclass(frozen=True, slots=True)
class AppliedLabel:
    """D29(b): an applied-label fact, pinned to its vocabulary revision."""

    label_key: str
    label: str
    vocabulary_revision: int
    applied_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "applied_at": self.applied_at.isoformat(),
            "label": self.label,
            "label_key": self.label_key,
            "vocabulary_revision": self.vocabulary_revision,
        }


class HumanWaitingState(StrEnum):
    WAITING = "waiting"
    NOT_WAITING = "not_waiting"


@dataclass(frozen=True, slots=True)
class HumanWaiting:
    """AC-TM-08: human-waiting derives only from a qualifying Attention finding."""

    state: HumanWaitingState
    finding_id: UUID | None = None
    kind_key: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        waiting = self.state is HumanWaitingState.WAITING
        complete = (
            self.finding_id is not None
            and self.kind_key is not None
            and self.reason_code is not None
        )
        if waiting != complete:
            raise ValueError("human-waiting must carry its finding, and only while waiting")

    def response_payload(self) -> dict[str, object]:
        if self.state is HumanWaitingState.NOT_WAITING:
            return {"state": "not_waiting"}
        return {
            "finding_id": str(self.finding_id),
            "kind_key": self.kind_key,
            "reason_code": self.reason_code,
            "state": "waiting",
        }


class BoardDeliverySurfaceState(StrEnum):
    NO_QUALIFYING_CHECKPOINT = "no_qualifying_checkpoint"
    QUALIFYING_CHECKPOINT = "qualifying_checkpoint"


@dataclass(frozen=True, slots=True)
class BoardDeliverySurfaceAvailability:
    """AC-PD-10: the ticket's qualifying checkpoint's pinned declaration."""

    state: BoardDeliverySurfaceState
    checkpoint_key: str | None = None
    declaration: DeliverySurfaceDeclaration | None = None

    def __post_init__(self) -> None:
        qualifying = self.state is BoardDeliverySurfaceState.QUALIFYING_CHECKPOINT
        complete = self.checkpoint_key is not None and self.declaration is not None
        if qualifying != complete:
            raise ValueError(
                "delivery-surface availability must carry its checkpoint, "
                "and only while one qualifies"
            )

    def response_payload(self) -> dict[str, object]:
        if self.state is BoardDeliverySurfaceState.NO_QUALIFYING_CHECKPOINT:
            return {"state": "no_qualifying_checkpoint"}
        if self.declaration is None:
            raise RuntimeError("qualifying delivery surface is missing its declaration")
        payload = self.declaration.response_payload()
        payload["checkpoint_key"] = self.checkpoint_key
        payload["state"] = "qualifying_checkpoint"
        return payload


_TENANT_UNKNOWN = TenantDisplayIdentity(TenantDisplayState.UNKNOWN, missing_source="not_derived")
_NOT_WAITING = HumanWaiting(HumanWaitingState.NOT_WAITING)
_NO_QUALIFYING_CHECKPOINT = BoardDeliverySurfaceAvailability(
    BoardDeliverySurfaceState.NO_QUALIFYING_CHECKPOINT
)


@dataclass(frozen=True, slots=True)
class BoardCard:
    ticket_id: UUID
    project_key: str
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
    display_key: str | None = None
    tenant_display_identity: TenantDisplayIdentity = _TENANT_UNKNOWN
    change_references: tuple[ChangeReference, ...] = ()
    applied_labels: tuple[AppliedLabel, ...] = ()
    human_waiting: HumanWaiting = _NOT_WAITING
    delivery_surface_availability: BoardDeliverySurfaceAvailability = _NO_QUALIFYING_CHECKPOINT
    inbox_thread_ids: tuple[UUID, ...] = ()

    def response_payload(self) -> dict[str, object]:
        return {
            "activity_class": self.activity_class,
            "applied_labels": [item.response_payload() for item in self.applied_labels],
            "assignee_id": str(self.assignee_id) if self.assignee_id else None,
            "blocker_opened_at": (
                self.blocker_opened_at.isoformat() if self.blocker_opened_at else None
            ),
            "blocker_reason": self.blocker_reason,
            "change_references": [item.response_payload() for item in self.change_references],
            "custodian_id": str(self.custodian_id),
            "delivery_facts": list(self.delivery_facts),
            "delivery_surface_availability": self.delivery_surface_availability.response_payload(),
            "display_key": self.display_key,
            "human_waiting": self.human_waiting.response_payload(),
            "inbox_thread_ids": [str(item) for item in self.inbox_thread_ids],
            "lane": self.lane.value,
            "priority": self.priority,
            "project_key": self.project_key,
            "risk": self.risk,
            "stage_key": self.stage_key,
            "stage_label": self.stage_key,
            "tenant_display_identity": self.tenant_display_identity.response_payload(),
            "ticket_id": str(self.ticket_id),
            "title": self.title,
            "underlying_lane": (self.underlying_lane.value if self.underlying_lane else None),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class BoardQuery:
    project_key: str
    lane: BoardLane | None = None
    priority: str | None = None
    stage_key: str | None = None
    custodian_id: UUID | None = None
    assignee_id: UUID | None = None
    risk: str | None = None
    source_kind: str | None = None
    source_ref: str | None = None


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


@dataclass(frozen=True, slots=True)
class InboxThreadSummary:
    last_message_at: datetime
    last_message_preview: str
    other_agent: str
    promoted_ticket_id: UUID | None
    thread_id: UUID
    unread_count: int

    def response_payload(self) -> dict[str, object]:
        return {
            "last_message_at": self.last_message_at.isoformat(),
            "last_message_preview": self.last_message_preview,
            "other_agent": self.other_agent,
            "promoted_ticket_id": (
                str(self.promoted_ticket_id) if self.promoted_ticket_id is not None else None
            ),
            "thread_id": str(self.thread_id),
            "unread_count": self.unread_count,
        }


@dataclass(frozen=True, slots=True)
class InboxThreadList:
    recipient: str
    threads: tuple[InboxThreadSummary, ...]
    total_unread: int
    unread_only: bool

    def response_payload(self) -> dict[str, object]:
        return {
            "recipient": self.recipient,
            "threads": [item.response_payload() for item in self.threads],
            "total_unread": self.total_unread,
            "unread_only": self.unread_only,
        }


@dataclass(frozen=True, slots=True)
class InboxCorrespondent:
    project_key: str
    seat_key: str

    def response_payload(self) -> dict[str, object]:
        return {"project_key": self.project_key, "seat_key": self.seat_key}


@dataclass(frozen=True, slots=True)
class InboxCorrespondentList:
    """Every address the authenticated principal can open a thread to, and its own seat.

    These are fewer than the registered seats, and that is the point: the send
    command resolves a recipient by ``(tenant_id, seat_key)``, so a key two
    seats share resolves to nobody, the reader's own seat resolves to itself,
    and a reader with no seat row cannot send at all. Each of those is left out
    here for the same reason the command refuses it, so a picker built on this
    list can offer nothing the record would not accept as an address. ``sender``
    is ``unaddressable`` exactly when this principal holds no seat row.
    """

    correspondents: tuple[InboxCorrespondent, ...]
    sender: str

    def response_payload(self) -> dict[str, object]:
        return {
            "correspondents": [item.response_payload() for item in self.correspondents],
            "sender": self.sender,
        }


@dataclass(frozen=True, slots=True)
class InboxMessage:
    from_seat: str
    message_id: UUID
    position: int
    sent_at: datetime
    text: str
    to: str

    def response_payload(self) -> dict[str, object]:
        return {
            "from": self.from_seat,
            "message_id": str(self.message_id),
            "position": self.position,
            "sent_at": self.sent_at.isoformat(),
            "text": self.text,
            "to": self.to,
        }


@dataclass(frozen=True, slots=True)
class InboxThread:
    messages: tuple[InboxMessage, ...]
    participants: tuple[str, str]
    promoted_ticket_id: UUID | None
    read_through_position: int
    thread_id: UUID

    def response_payload(self) -> dict[str, object]:
        return {
            "messages": [item.response_payload() for item in self.messages],
            "participants": list(self.participants),
            "promoted_ticket_id": (
                str(self.promoted_ticket_id) if self.promoted_ticket_id is not None else None
            ),
            "read_through_position": self.read_through_position,
            "thread_id": str(self.thread_id),
        }


class _ProjectionStore(Protocol):
    def catch_up(self, tenant_id: UUID, through_watermark: int | None = None) -> BoardView: ...

    def board(self, actor: Actor, query: BoardQuery) -> BoardView: ...

    def list_inbox(self, actor: Actor, *, unread: bool) -> InboxThreadList: ...

    def list_inbox_correspondents(self, actor: Actor) -> InboxCorrespondentList: ...

    def read_inbox(self, actor: Actor, thread_id: UUID) -> InboxThread | None: ...

    def inbox_read_state(self, actor: Actor, thread_id: UUID) -> _InboxReadState | None: ...

    def rebuild(self, tenant_id: UUID) -> BoardView: ...

    def health(
        self, tenant_id: UUID, durability: DurabilityHealth, *, now: datetime
    ) -> ControlHealth: ...

    def cutover_health(self, actor: Actor) -> CtowerProjectCutoverHealth: ...

    def project_delivery(self, actor: Actor, project_key: str) -> ProjectDeliveryView | None: ...

    def reconcile_project_delivery(self, tenant_id: UUID, *, now: datetime) -> int: ...

    def rebuild_project_delivery(self, tenant_id: UUID, *, now: datetime) -> int: ...


class Projections:
    """Expose catch-up, read, and deterministic rebuild without mutation commands."""

    def __init__(self, store: _ProjectionStore) -> None:
        self._store = store

    def catch_up(self, tenant_id: UUID, through_watermark: int | None = None) -> BoardView:
        return self._store.catch_up(tenant_id, through_watermark)

    def board(self, actor: Actor, query: BoardQuery) -> BoardView:
        return self._store.board(actor, query)

    def list_inbox(self, actor: Actor, *, unread: bool = False) -> InboxThreadList:
        return self._store.list_inbox(actor, unread=unread)

    def list_inbox_correspondents(self, actor: Actor) -> InboxCorrespondentList:
        """Read the registered seats this principal may address, never invent one."""

        return self._store.list_inbox_correspondents(actor)

    def read_inbox(self, actor: Actor, thread_id: UUID) -> InboxThread | None:
        return self._store.read_inbox(actor, thread_id)

    def inbox_read_state(self, actor: Actor, thread_id: UUID) -> _InboxReadState | None:
        return self._store.inbox_read_state(actor, thread_id)

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

    def reconcile_project_delivery(self, tenant_id: UUID, *, now: datetime) -> int:
        """Reconcile changed or freshness-due rows outside request handling."""

        return self._store.reconcile_project_delivery(tenant_id, now=now)

    def rebuild_project_delivery(self, tenant_id: UUID, *, now: datetime) -> int:
        """Delete and deterministically rebuild disposable Project Delivery rows."""

        return self._store.rebuild_project_delivery(tenant_id, now=now)


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
        project_key=facts.project_key,
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
