"""Strict spawn-custody payloads and the one authored spawn lifecycle machine.

A spawn record is the operator's pre-execution commitment (R2982/R3000,
CT-I1-034): who/what/why/where of a crew dispatch captured BEFORE the substrate
drives anything. Like work sessions, it is a Record fact, not a vendor handle;
every field is authored, bounded, and free of credential, PHI, or personal
content by contract.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

__all__ = [
    "INITIAL_SPAWN_STATE",
    "SpawnEventPayload",
    "SpawnRecordedPayload",
    "SpawnState",
    "SpawnTransitionedPayload",
    "spawn_payload_from_mapping",
    "spawn_transition_allowed",
]

_MAX_REASON = 4096
_MAX_REFERENCE = 1024
_MAX_CREW_NAME = 255
_MAX_SEAT_KEY = 255
_MAX_HARNESS = 64
_MAX_MODEL = 128
_MAX_EFFORT = 64
_STABLE_NAME = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_PROJECT_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class SpawnState(StrEnum):
    """The authored spawn lifecycle: linear, no skipping, three terminal states."""

    REQUESTED = "requested"
    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REAPED = "reaped"


INITIAL_SPAWN_STATE = SpawnState.REQUESTED

_ALLOWED: dict[SpawnState, frozenset[SpawnState]] = {
    SpawnState.REQUESTED: frozenset({SpawnState.ACCEPTED, SpawnState.FAILED}),
    SpawnState.ACCEPTED: frozenset({SpawnState.RUNNING, SpawnState.FAILED}),
    SpawnState.RUNNING: frozenset({SpawnState.COMPLETED, SpawnState.FAILED, SpawnState.REAPED}),
    SpawnState.COMPLETED: frozenset(),
    SpawnState.FAILED: frozenset(),
    SpawnState.REAPED: frozenset(),
}


def spawn_transition_allowed(from_state: SpawnState, to_state: SpawnState) -> bool:
    """One authored lifecycle: requested -> accepted -> running -> one terminal."""

    return to_state in _ALLOWED[from_state]


@dataclass(frozen=True, slots=True)
class SpawnRecordedPayload:
    """Who/what/why/where of one crew dispatch, captured before driving."""

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

    def __post_init__(self) -> None:
        _uuid("spawn_id", self.spawn_id)
        if (
            not isinstance(self.project_key, str)
            or _PROJECT_KEY.fullmatch(self.project_key) is None
        ):
            raise ValueError("project_key is outside the authored event contract")
        _stable("seat_key", self.seat_key)
        _bounded("crew_name", self.crew_name, maximum=_MAX_CREW_NAME)
        _bounded("task_file_ref", self.task_file_ref, maximum=_MAX_REFERENCE)
        _bounded("worktree_path", self.worktree_path, maximum=_MAX_REFERENCE)
        _bounded("harness", self.harness, maximum=_MAX_HARNESS)
        _bounded("model", self.model, maximum=_MAX_MODEL)
        if self.effort is not None:
            _bounded("effort", self.effort, maximum=_MAX_EFFORT)
        if self.workspace_id is not None:
            _uuid("workspace_id", self.workspace_id)

    def to_mapping(self) -> dict[str, object]:
        return {
            "spawn_id": str(self.spawn_id),
            "project_key": self.project_key,
            "seat_key": self.seat_key,
            "crew_name": self.crew_name,
            "task_file_ref": self.task_file_ref,
            "worktree_path": self.worktree_path,
            "harness": self.harness,
            "model": self.model,
            "effort": self.effort,
            "workspace_id": None if self.workspace_id is None else str(self.workspace_id),
        }


@dataclass(frozen=True, slots=True)
class SpawnTransitionedPayload:
    """One authored lifecycle movement on one spawn record."""

    spawn_id: UUID
    from_state: SpawnState
    to_state: SpawnState
    transition_number: int
    reason: str | None

    def __post_init__(self) -> None:
        _uuid("spawn_id", self.spawn_id)
        if type(self.transition_number) is not int or self.transition_number < 1:
            raise ValueError("spawn transition number must be a positive integer")
        if self.reason is not None:
            _bounded("reason", self.reason, maximum=_MAX_REASON)
        if not spawn_transition_allowed(self.from_state, self.to_state):
            raise ValueError("spawn transition is outside the authored lifecycle")

    def to_mapping(self) -> dict[str, object]:
        return {
            "spawn_id": str(self.spawn_id),
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "transition_number": self.transition_number,
            "reason": self.reason,
        }


type SpawnEventPayload = SpawnRecordedPayload | SpawnTransitionedPayload

_SPAWN_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    "spawn.recorded": frozenset(
        {
            "spawn_id",
            "project_key",
            "seat_key",
            "crew_name",
            "task_file_ref",
            "worktree_path",
            "harness",
            "model",
            "effort",
            "workspace_id",
        }
    ),
    "spawn.transitioned": frozenset(
        {"spawn_id", "from_state", "to_state", "transition_number", "reason"}
    ),
}


def spawn_payload_from_mapping(kind: str, payload: Mapping[str, object]) -> SpawnEventPayload:
    """Rebuild one typed spawn payload at the persistence read boundary."""

    expected = _SPAWN_PAYLOAD_FIELDS.get(kind)
    if expected is None:
        raise ValueError(f"{kind} is not a spawn-custody event")
    if set(payload) != expected:
        raise ValueError("event payload fields do not match the authored variant")
    if kind == "spawn.recorded":
        effort = payload["effort"]
        workspace_id = payload["workspace_id"]
        return SpawnRecordedPayload(
            spawn_id=_uuid_value(payload["spawn_id"], "spawn_id"),
            project_key=_string(payload["project_key"], "project_key"),
            seat_key=_string(payload["seat_key"], "seat_key"),
            crew_name=_string(payload["crew_name"], "crew_name"),
            task_file_ref=_string(payload["task_file_ref"], "task_file_ref"),
            worktree_path=_string(payload["worktree_path"], "worktree_path"),
            harness=_string(payload["harness"], "harness"),
            model=_string(payload["model"], "model"),
            effort=None if effort is None else _string(effort, "effort"),
            workspace_id=None
            if workspace_id is None
            else _uuid_value(workspace_id, "workspace_id"),
        )
    reason = payload["reason"]
    return SpawnTransitionedPayload(
        spawn_id=_uuid_value(payload["spawn_id"], "spawn_id"),
        from_state=_state(payload["from_state"]),
        to_state=_state(payload["to_state"]),
        transition_number=_integer(payload["transition_number"], "transition_number"),
        reason=None if reason is None else _string(reason, "reason"),
    )


def _state(value: object) -> SpawnState:
    if not isinstance(value, str) or value not in set(SpawnState):
        raise ValueError("spawn state is outside the authored event contract")
    return SpawnState(value)


def _bounded(label: str, value: object, *, maximum: int) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not 1 <= len(value) <= maximum:
        raise ValueError(f"{label} is outside the authored event contract")


def _stable(label: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if _STABLE_NAME.fullmatch(value) is None:
        raise ValueError(f"{label} is outside the authored event contract")


def _uuid(label: str, value: object) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{label} must be a UUID")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _uuid_value(value: object, label: str) -> UUID:
    return UUID(_string(value, label))


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    return value
