"""Typed project-scoped event-feed read model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ctower_kernel.record.interface import AuditEvent

__all__ = ["ProjectEventPage"]


@dataclass(frozen=True, slots=True)
class ProjectEventPage:
    """One record-position cursor page of a single project's feed-scoped events."""

    project_key: str
    events: tuple[AuditEvent, ...]
    next_cursor: int | None

    def response_payload(self) -> dict[str, object]:
        return {
            "events": [event.response_payload() for event in self.events],
            "next_cursor": self.next_cursor,
            "project_key": self.project_key,
        }
