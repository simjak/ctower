"""Strict generic Workflow graph parsing and immutable identity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

__all__ = ["ActivityClass", "Stage", "Transition", "WorkflowGraph"]

_STABLE_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")
_VERSIONED_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")


class ActivityClass(StrEnum):
    """Domain-neutral Board activity metadata."""

    WORK = "work"
    VERIFICATION = "verification"


@dataclass(frozen=True, slots=True)
class Stage:
    """One authored graph node."""

    key: str
    activity_class: ActivityClass

    def __post_init__(self) -> None:
        if _STABLE_KEY.fullmatch(self.key) is None:
            raise ValueError("stage key must be stable")


@dataclass(frozen=True, slots=True)
class Transition:
    """One directed edge guarded by a versioned predicate."""

    source: str
    destination: str
    predicate_ref: str

    def __post_init__(self) -> None:
        if _STABLE_KEY.fullmatch(self.source) is None:
            raise ValueError("transition source must be stable")
        if _STABLE_KEY.fullmatch(self.destination) is None:
            raise ValueError("transition destination must be stable")
        if _VERSIONED_REFERENCE.fullmatch(self.predicate_ref) is None:
            raise ValueError("transition predicate must be versioned")


def _validate_graph(graph: WorkflowGraph) -> None:
    """Validate graph structure separately from component identity."""

    stage_keys = {stage.key for stage in graph.stages}
    if not graph.stages or len(stage_keys) != len(graph.stages):
        raise ValueError("workflow stages must be nonempty and unique")
    if graph.initial_stage not in stage_keys:
        raise ValueError("workflow initial stage must reference one declared stage")
    edges = {(edge.source, edge.destination) for edge in graph.transitions}
    if len(edges) != len(graph.transitions):
        raise ValueError("workflow edges must be unique")
    if any(
        edge.source not in stage_keys or edge.destination not in stage_keys
        for edge in graph.transitions
    ):
        raise ValueError("workflow edges must reference declared stages")
    for reference in (graph.execution_policy_ref, graph.gate_policy_ref):
        if reference is not None and _VERSIONED_REFERENCE.fullmatch(reference) is None:
            raise ValueError("workflow policy references must be versioned")


@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    """Immutable authored graph revision and exact semantic digest."""

    key: str
    revision: int
    initial_stage: str
    stages: tuple[Stage, ...]
    transitions: tuple[Transition, ...]
    execution_policy_ref: str | None = None
    gate_policy_ref: str | None = None

    def __post_init__(self) -> None:
        if _STABLE_KEY.fullmatch(self.key) is None:
            raise ValueError("workflow key must be stable")
        if self.revision < 1:
            raise ValueError("workflow revision must be positive")
        _validate_graph(self)

    @property
    def reference(self) -> str:
        """Return the immutable component reference."""

        return f"{self.key}@{self.revision}"

    @property
    def digest(self) -> str:
        """Return an exact digest over fields that control graph evaluation."""

        payload = {
            "initial_stage": self.initial_stage,
            "policy_refs": {
                "execution": self.execution_policy_ref,
                "gates": self.gate_policy_ref,
            },
            "reference": self.reference,
            "stages": [
                {"activity_class": stage.activity_class.value, "key": stage.key}
                for stage in self.stages
            ],
            "transitions": [
                {
                    "from": edge.source,
                    "predicate_ref": edge.predicate_ref,
                    "to": edge.destination,
                }
                for edge in self.transitions
            ],
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> WorkflowGraph:
        """Parse one strict authored Workflow payload without a schema runtime."""

        _require_keys(
            payload,
            {
                "schema",
                "status",
                "key",
                "revision",
                "initial_stage",
                "input_contract",
                "terminal_contract",
                "policy_refs",
                "stages",
                "transitions",
                "failure_routes",
                "note",
            },
        )
        policy_refs = _validate_metadata(payload)
        return cls(
            key=_string(payload["key"], "key"),
            revision=_integer(payload["revision"], "revision"),
            initial_stage=_string(payload["initial_stage"], "initial_stage"),
            stages=tuple(_stage(item) for item in _objects(payload["stages"], "stages")),
            transitions=tuple(
                _transition(item) for item in _objects(payload["transitions"], "transitions")
            ),
            execution_policy_ref=_string(policy_refs["execution"], "execution"),
            gate_policy_ref=_string(policy_refs["gates"], "gates"),
        )


def _validate_metadata(payload: Mapping[str, object]) -> Mapping[str, object]:
    if payload["schema"] != "ctower.workflow/v1":
        raise ValueError("workflow schema is unsupported")
    if payload["status"] not in {"draft", "staged", "published", "superseded", "revoked"}:
        raise ValueError("workflow status is unsupported")
    for field in ("input_contract", "terminal_contract"):
        if _STABLE_KEY.fullmatch(_string(payload[field], field)) is None:
            raise ValueError(f"{field} must be stable")
    if not _string(payload["note"], "note"):
        raise ValueError("note must be nonempty")
    policy_refs = _object(payload["policy_refs"], "policy_refs")
    _require_keys(policy_refs, {"execution", "gates"})
    if any(
        _VERSIONED_REFERENCE.fullmatch(_string(value, key)) is None
        for key, value in policy_refs.items()
    ):
        raise ValueError("workflow policy references must be versioned")
    for route in _objects(payload["failure_routes"], "failure_routes"):
        _validate_failure_route(route)
    return policy_refs


def _validate_failure_route(payload: Mapping[str, object]) -> None:
    _require_keys(payload, {"from", "failure_class_ref", "to"})
    if any(
        _STABLE_KEY.fullmatch(_string(payload[field], f"failure_route.{field}")) is None
        for field in ("from", "to")
    ):
        raise ValueError("failure route stages must be stable")
    if (
        _VERSIONED_REFERENCE.fullmatch(
            _string(payload["failure_class_ref"], "failure_route.failure_class_ref")
        )
        is None
    ):
        raise ValueError("failure route class must be versioned")


def _stage(payload: Mapping[str, object]) -> Stage:
    _require_keys(payload, {"key", "activity_class"})
    return Stage(
        key=_string(payload["key"], "stage.key"),
        activity_class=ActivityClass(_string(payload["activity_class"], "activity_class")),
    )


def _transition(payload: Mapping[str, object]) -> Transition:
    _require_keys(payload, {"from", "to", "predicate_ref"})
    return Transition(
        source=_string(payload["from"], "transition.from"),
        destination=_string(payload["to"], "transition.to"),
        predicate_ref=_string(payload["predicate_ref"], "transition.predicate_ref"),
    )


def _objects(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise TypeError(f"{label} must be an array of objects")
    return tuple(_object(item, label) for item in value)


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _require_keys(payload: Mapping[str, object], expected: set[str]) -> None:
    if set(payload) != expected:
        raise ValueError("workflow payload fields do not match the authored contract")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    return value
