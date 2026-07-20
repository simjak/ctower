"""Generic, version-pinned Workflow graph evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from ctower_kernel.telemetry import TelemetryContext

if TYPE_CHECKING:
    from ctower_kernel.record import RecordProblem

__all__ = [
    "ActivityClass",
    "ResolveClose",
    "Stage",
    "Transition",
    "Workflow",
    "WorkflowActor",
    "WorkflowCommand",
    "WorkflowContextSnapshot",
    "WorkflowDecision",
    "WorkflowGraph",
    "WorkflowMutation",
    "WorkflowReceipt",
]

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


@dataclass(frozen=True, slots=True)
class WorkflowGraph:
    """Immutable authored graph revision."""

    key: str
    revision: int
    initial_stage: str
    stages: tuple[Stage, ...]
    transitions: tuple[Transition, ...]

    def __post_init__(self) -> None:
        if _STABLE_KEY.fullmatch(self.key) is None:
            raise ValueError("workflow key must be stable")
        if self.revision < 1:
            raise ValueError("workflow revision must be positive")
        stage_keys = {stage.key for stage in self.stages}
        if not self.stages or len(stage_keys) != len(self.stages):
            raise ValueError("workflow stages must be nonempty and unique")
        if self.initial_stage not in stage_keys:
            raise ValueError("workflow initial stage must reference one declared stage")
        edges = {(edge.source, edge.destination) for edge in self.transitions}
        if len(edges) != len(self.transitions):
            raise ValueError("workflow edges must be unique")
        if any(
            edge.source not in stage_keys or edge.destination not in stage_keys
            for edge in self.transitions
        ):
            raise ValueError("workflow edges must reference declared stages")

    @property
    def reference(self) -> str:
        """Return the immutable component reference."""

        return f"{self.key}@{self.revision}"

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> WorkflowGraph:
        """Parse one strict authored Workflow payload without a runtime schema dependency."""

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
        _validate_metadata(payload)
        stages = tuple(_stage(item) for item in _objects(payload["stages"], "stages"))
        transitions = tuple(
            _transition(item) for item in _objects(payload["transitions"], "transitions")
        )
        return cls(
            key=_string(payload["key"], "key"),
            revision=_integer(payload["revision"], "revision"),
            initial_stage=_string(payload["initial_stage"], "initial_stage"),
            stages=stages,
            transitions=transitions,
        )


@dataclass(frozen=True, slots=True)
class WorkflowContextSnapshot:
    """Immutable facts supplied to one evaluation."""

    workflow_ref: str
    current_stage: str
    satisfied_predicates: frozenset[str]
    run_started: bool


@dataclass(frozen=True, slots=True)
class WorkflowCommand:
    """Requested graph movement."""

    destination_stage: str


@dataclass(frozen=True, slots=True)
class WorkflowDecision:
    """A fail-closed evaluation result, not a persisted fact."""

    accepted: bool
    reason: str
    activity_class: ActivityClass | None = None
    predicate_ref: str | None = None
    initial_stage: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowActor:
    """Minimal authenticated authority facts used by Workflow."""

    principal_id: UUID
    tenant_id: UUID


@dataclass(frozen=True, slots=True)
class WorkflowMutation:
    """Version-checked request to traverse one declared edge."""

    client_command_id: UUID
    ticket_id: UUID
    workflow_ref: str
    expected_version: int
    source_stage: str
    destination_stage: str

    def request_payload(self) -> dict[str, object]:
        """Return the complete idempotency payload."""

        return {
            "destination_stage": self.destination_stage,
            "expected_version": self.expected_version,
            "source_stage": self.source_stage,
            "ticket_id": str(self.ticket_id),
            "workflow_ref": self.workflow_ref,
        }


@dataclass(frozen=True, slots=True)
class ResolveClose:
    """Request atomic resolved and closed lifecycle facts."""

    client_command_id: UUID
    ticket_id: UUID
    workflow_ref: str
    expected_version: int

    def request_payload(self) -> dict[str, object]:
        """Return the complete idempotency payload."""

        return {
            "expected_version": self.expected_version,
            "ticket_id": str(self.ticket_id),
            "workflow_ref": self.workflow_ref,
        }


@dataclass(frozen=True, slots=True)
class WorkflowReceipt:
    """Committed Workflow state retained for exact replay."""

    command_id: UUID
    event_ids: tuple[UUID, ...]
    workflow_run_id: UUID
    ticket_id: UUID
    workflow_ref: str
    stage: str
    activity_class: ActivityClass
    version: int
    lifecycle_facts: tuple[str, ...] = ()

    def response_payload(self) -> dict[str, object]:
        """Return the stable public command receipt."""

        return {
            "activity_class": self.activity_class.value,
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "lifecycle_facts": list(self.lifecycle_facts),
            "stage": self.stage,
            "ticket_id": str(self.ticket_id),
            "version": self.version,
            "workflow_ref": self.workflow_ref,
            "workflow_run_id": str(self.workflow_run_id),
        }


class _WorkflowWriter(Protocol):
    def advance_workflow(
        self,
        evaluator: Workflow,
        actor: WorkflowActor,
        mutation: WorkflowMutation,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem: ...

    def close_workflow(
        self,
        evaluator: Workflow,
        actor: WorkflowActor,
        command: ResolveClose,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem: ...


class Workflow:
    """Evaluate graph legality without domain-stage branches or persistence imports."""

    def __init__(
        self,
        graphs: tuple[WorkflowGraph, ...],
        *,
        writer: _WorkflowWriter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._graphs = {graph.reference: graph for graph in graphs}
        if len(self._graphs) != len(graphs):
            raise ValueError("workflow graph references must be unique")
        self._writer = writer
        self._clock = clock or (lambda: datetime.now(UTC))

    def advance(
        self,
        actor: WorkflowActor,
        mutation: WorkflowMutation,
        *,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem:
        """Commit or replay one legal graph transition."""

        if self._writer is None:
            raise RuntimeError("workflow persistence is not configured")
        return self._writer.advance_workflow(
            self,
            actor,
            mutation,
            request_digest=_digest(mutation.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )

    def resolve_close(
        self,
        actor: WorkflowActor,
        command: ResolveClose,
        *,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem:
        """Atomically append terminal lifecycle facts after rechecking proof."""

        if self._writer is None:
            raise RuntimeError("workflow persistence is not configured")
        return self._writer.close_workflow(
            self,
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )

    def evaluate(
        self, snapshot: WorkflowContextSnapshot, command: WorkflowCommand
    ) -> WorkflowDecision:
        """Evaluate one requested transition against pinned graph facts."""

        graph = self._graphs.get(snapshot.workflow_ref)
        if graph is None:
            return WorkflowDecision(accepted=False, reason="workflow-version-unknown")
        if not snapshot.run_started and snapshot.current_stage != graph.initial_stage:
            return WorkflowDecision(accepted=False, reason="initial-stage-required")
        edge = next(
            (
                candidate
                for candidate in graph.transitions
                if candidate.source == snapshot.current_stage
                and candidate.destination == command.destination_stage
            ),
            None,
        )
        if edge is None:
            return WorkflowDecision(accepted=False, reason="transition-not-declared")
        if edge.predicate_ref not in snapshot.satisfied_predicates:
            return WorkflowDecision(
                accepted=False,
                reason="predicate-unsatisfied",
                predicate_ref=edge.predicate_ref,
            )
        activity = next(
            stage.activity_class for stage in graph.stages if stage.key == command.destination_stage
        )
        return WorkflowDecision(
            accepted=True,
            reason="accepted",
            activity_class=activity,
            predicate_ref=edge.predicate_ref,
            initial_stage=graph.initial_stage,
        )

    def is_terminal(self, workflow_ref: str, stage_key: str) -> bool:
        """Return whether a known stage has no declared outgoing edge."""

        graph = self._graphs.get(workflow_ref)
        if graph is None or not any(stage.key == stage_key for stage in graph.stages):
            return False
        return not any(edge.source == stage_key for edge in graph.transitions)


def _digest(payload: dict[str, object]) -> bytes:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).digest()


def _validate_metadata(payload: Mapping[str, object]) -> None:
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


def _validate_failure_route(payload: Mapping[str, object]) -> None:
    _require_keys(payload, {"from", "failure_class_ref", "to"})
    if any(
        _STABLE_KEY.fullmatch(_string(payload[field], f"failure_route.{field}")) is None
        for field in ("from", "to")
    ):
        raise ValueError("failure route stages must be stable")
    reference = _string(payload["failure_class_ref"], "failure_route.failure_class_ref")
    if _VERSIONED_REFERENCE.fullmatch(reference) is None:
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
