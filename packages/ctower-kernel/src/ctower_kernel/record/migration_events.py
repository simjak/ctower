"""Strict payload for the restricted ctower-project migration stream."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

__all__ = ["MigrationChangedPayload"]

_OPERATIONS = frozenset(
    {
        "run_created",
        "export_equality_bound",
        "alias_plan_bound",
        "ticket_seed",
        "exact_alias",
        "ticket_relation",
        "source_link",
        "correction_appended",
        "reconciled",
        "fence_observed",
    }
)
MAX_TARGET_LENGTH = 256


@dataclass(frozen=True, slots=True)
class MigrationChangedPayload:
    """One migration fact; it never represents epoch activation or fence arming."""

    operation: str
    run_id: UUID | None
    cutover_id: UUID | None
    project_key: str
    target_id: str

    def __post_init__(self) -> None:
        if self.operation not in _OPERATIONS:
            raise ValueError("migration operation is outside the restricted event contract")
        if self.operation == "fence_observed":
            if self.run_id is not None or self.cutover_id is not None:
                raise ValueError("fence observations do not carry import-run authority")
        elif not isinstance(self.run_id, UUID) or not isinstance(self.cutover_id, UUID):
            raise TypeError("migration run and cutover identity must be UUIDs")
        if self.project_key != "ctower":
            raise ValueError("migration events are restricted to the ctower project")
        if not self.target_id or len(self.target_id) > MAX_TARGET_LENGTH:
            raise ValueError("migration event target is outside the authored contract")

    def to_mapping(self) -> dict[str, object]:
        return {
            "cutover_id": str(self.cutover_id) if self.cutover_id is not None else None,
            "operation": self.operation,
            "project_key": self.project_key,
            "run_id": str(self.run_id) if self.run_id is not None else None,
            "target_id": self.target_id,
        }
