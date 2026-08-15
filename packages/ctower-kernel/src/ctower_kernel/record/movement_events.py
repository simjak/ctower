"""Typed project-scoped movement read model (transition facts only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from ctower_kernel.record.interface import Actor, RecordProblem
    from ctower_kernel.telemetry import TelemetryContext

__all__ = [
    "MovementCountList",
    "MovementCountRow",
    "MovementEvent",
    "MovementEventPage",
    "MovementEventStore",
]


@dataclass(frozen=True, slots=True)
class MovementCountRow:
    """One transition fact counted for the digest, keyed by project and stages."""

    project_key: str
    source_stage: str
    stage: str
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class MovementCountList:
    """Every tenant transition fact plus the ledger watermark at read time."""

    rows: tuple[MovementCountRow, ...]
    watermark: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class MovementEvent:
    """One Ticket-linked transition fact; never an exhaustive Ticket snapshot."""

    event_id: UUID
    record_position: int
    ticket_id: UUID
    from_stage: str
    to_stage: str
    evaluation_ref: str
    workflow_ref: str
    workflow_version: int
    occurred_at: datetime

    def response_payload(self) -> dict[str, object]:
        return {
            "evaluation_ref": self.evaluation_ref,
            "event_id": str(self.event_id),
            "from_stage": self.from_stage,
            "occurred_at": self.occurred_at.isoformat(),
            "record_position": self.record_position,
            "ticket_id": str(self.ticket_id),
            "to_stage": self.to_stage,
            "workflow_ref": self.workflow_ref,
            "workflow_version": self.workflow_version,
        }


@dataclass(frozen=True, slots=True)
class MovementEventPage:
    """One record-position cursor page of a project's transition facts."""

    project_key: str
    events: tuple[MovementEvent, ...]
    next_cursor: int | None

    def response_payload(self) -> dict[str, object]:
        return {
            "events": [event.response_payload() for event in self.events],
            "next_cursor": self.next_cursor,
            "project_key": self.project_key,
        }


class MovementEventStore(Protocol):
    """Record boundary for project movement reads and digest counts."""

    def movement_events(
        self,
        actor: Actor,
        project_key: str,
        *,
        cursor: int,
        limit: int,
        telemetry: TelemetryContext,
    ) -> MovementEventPage | RecordProblem: ...

    def movement_counts(
        self, actor: Actor, *, telemetry: TelemetryContext
    ) -> MovementCountList | RecordProblem: ...
