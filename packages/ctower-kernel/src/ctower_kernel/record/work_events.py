"""Strict Work event payload kept separate from Record envelope mechanics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

__all__ = ["WorkChangedPayload"]

_FIELDS: dict[str, frozenset[str]] = {
    "priority_changed": frozenset(
        {
            "authority",
            "from_priority",
            "policy_ref",
            "reason",
            "to_priority",
            "urgent_evidence_ref",
        }
    ),
    "assignment_changed": frozenset(
        {"assignment_kind", "from_principal_id", "reason", "scope_ref", "to_principal_id"}
    ),
    "admitted": frozenset({"episode_number", "reason"}),
    "deferred": frozenset({"episode_number", "reason", "review_after"}),
    "blocker_opened": frozenset({"blocker_id", "board_impact", "reason"}),
    "blocker_resolved": frozenset({"blocker_id", "reason", "resolution_evidence_ref"}),
    "reopened": frozenset({"episode_number", "priority", "reason"}),
    "relation_added": frozenset({"relation_kind", "reason", "target_ticket_id"}),
}
INITIAL_WORK_VERSION = 2


@dataclass(frozen=True, slots=True)
class WorkChangedPayload:
    """One typed Work mutation without a writable lifecycle or Board status."""

    operation: str
    ticket_id: UUID
    work_version: int
    data: Mapping[str, object]

    def __post_init__(self) -> None:
        expected = _FIELDS.get(self.operation)
        if expected is None or set(self.data) != expected:
            raise ValueError("Work event data does not match its authored operation")
        if not isinstance(self.ticket_id, UUID):
            raise TypeError("ticket_id must be a UUID")
        if self.work_version < INITIAL_WORK_VERSION:
            raise ValueError("Work change version must follow ticket creation")

    def to_mapping(self) -> dict[str, object]:
        return {
            "data": dict(self.data),
            "operation": self.operation,
            "ticket_id": str(self.ticket_id),
            "work_version": self.work_version,
        }
