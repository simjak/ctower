"""Typed spawn-record commands, receipts, and read models for R2982."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

__all__ = [
    "SpawnRecordCreate",
    "SpawnRecordGet",
    "SpawnRecordList",
    "SpawnRecordProblem",
    "SpawnRecordRow",
    "SpawnRecordTransitionCommand",
    "SpawnRecordTransitionRow",
]


@dataclass(frozen=True, slots=True)
class SpawnRecordCreate:
    """Command to record a new crew spawn before dispatch."""

    client_command_id: UUID
    project_key: str
    seat_key: str
    crew_name: str
    task_file_ref: str
    worktree_path: str
    harness: str
    model: str
    effort: str | None
    workspace_id: UUID | None

    def request_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "project_key": self.project_key,
            "seat_key": self.seat_key,
            "crew_name": self.crew_name,
            "task_file_ref": self.task_file_ref,
            "worktree_path": self.worktree_path,
            "harness": self.harness,
            "model": self.model,
        }
        if self.effort is not None:
            payload["effort"] = self.effort
        if self.workspace_id is not None:
            payload["workspace_id"] = str(self.workspace_id)
        return payload


@dataclass(frozen=True, slots=True)
class SpawnRecordTransitionCommand:
    """Append-only transition fact for a spawn record."""

    client_command_id: UUID
    spawn_id: UUID
    to_status: str
    reason: str | None

    def request_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "spawn_id": str(self.spawn_id),
            "to_status": self.to_status,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True, slots=True)
class SpawnRecordTransitionRow:
    """One append-only transition fact."""

    transition_id: UUID
    spawn_id: UUID
    from_status: str
    to_status: str
    reason: str | None
    principal_id: UUID
    transitioned_at: datetime

    def response_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "transition_id": str(self.transition_id),
            "spawn_id": str(self.spawn_id),
            "from_status": self.from_status,
            "to_status": self.to_status,
            "principal_id": str(self.principal_id),
            "transitioned_at": self.transitioned_at.isoformat(),
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True, slots=True)
class SpawnRecordRow:
    """One spawn record as returned from reads."""

    spawn_id: UUID
    project_key: str
    seat_key: str
    crew_name: str
    task_file_ref: str
    worktree_path: str
    harness: str
    model: str
    effort: str | None
    workspace_id: UUID | None
    status: str
    principal_id: UUID
    created_at: datetime
    updated_at: datetime
    transitions: tuple[SpawnRecordTransitionRow, ...]

    def response_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "spawn_id": str(self.spawn_id),
            "project_key": self.project_key,
            "seat_key": self.seat_key,
            "crew_name": self.crew_name,
            "task_file_ref": self.task_file_ref,
            "worktree_path": self.worktree_path,
            "harness": self.harness,
            "model": self.model,
            "status": self.status,
            "principal_id": str(self.principal_id),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "transitions": [t.response_payload() for t in self.transitions],
        }
        if self.effort is not None:
            payload["effort"] = self.effort
        if self.workspace_id is not None:
            payload["workspace_id"] = str(self.workspace_id)
        return payload


@dataclass(frozen=True, slots=True)
class SpawnRecordList:
    """List of spawn records matching a query."""

    records: tuple[SpawnRecordRow, ...]

    def response_payload(self) -> dict[str, object]:
        return {
            "records": [r.response_payload() for r in self.records],
        }


@dataclass(frozen=True, slots=True)
class SpawnRecordGet:
    """Single spawn record with transitions."""

    record: SpawnRecordRow

    def response_payload(self) -> dict[str, object]:
        return self.record.response_payload()


@dataclass(frozen=True, slots=True)
class SpawnRecordProblem:
    """Typed problem from spawn record operations."""

    code: str
    detail: str
    status: int
    title: str
    command_id: UUID | None = None

    def response_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "detail": self.detail,
            "status": self.status,
            "title": self.title,
        }
        if self.command_id is not None:
            payload["command_id"] = str(self.command_id)
        return payload
