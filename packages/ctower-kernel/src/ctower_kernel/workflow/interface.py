"""Generic, version-pinned Workflow graph evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.workflow._graph import ActivityClass, Stage, Transition, WorkflowGraph

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
    "WorkflowStart",
]

_VERSIONED_REFERENCE = re.compile(r"^[a-z][a-z0-9._-]*@[1-9][0-9]*$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


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
class WorkflowStart:
    """Exact Workflow and compatible policy snapshot pin."""

    client_command_id: UUID
    ticket_id: UUID
    workflow_ref: str
    workflow_digest: str
    execution_policy_ref: str
    execution_policy_digest: str
    gate_policy_ref: str
    gate_policy_digest: str
    evidence_policy_ref: str
    evidence_policy_digest: str

    def request_payload(self) -> dict[str, object]:
        """Return the complete idempotency payload."""

        return {
            "evidence_policy_digest": self.evidence_policy_digest,
            "evidence_policy_ref": self.evidence_policy_ref,
            "execution_policy_digest": self.execution_policy_digest,
            "execution_policy_ref": self.execution_policy_ref,
            "gate_policy_digest": self.gate_policy_digest,
            "gate_policy_ref": self.gate_policy_ref,
            "ticket_id": str(self.ticket_id),
            "workflow_digest": self.workflow_digest,
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
    def start_workflow(
        self,
        evaluator: Workflow,
        actor: WorkflowActor,
        command: WorkflowStart,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem: ...

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
        policy_digests: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._graphs = {graph.reference: graph for graph in graphs}
        if len(self._graphs) != len(graphs):
            raise ValueError("workflow graph references must be unique")
        self._writer = writer
        self._policy_digests = dict(policy_digests or {})
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

    def start(
        self,
        actor: WorkflowActor,
        command: WorkflowStart,
        *,
        telemetry: TelemetryContext,
    ) -> WorkflowReceipt | RecordProblem:
        """Commit or exactly replay one immutable Workflow/policy pin."""

        if self._writer is None:
            raise RuntimeError("workflow persistence is not configured")
        return self._writer.start_workflow(
            self,
            actor,
            command,
            request_digest=_digest(command.request_payload()),
            now=self._clock(),
            telemetry=telemetry,
        )

    def validate_start(self, command: WorkflowStart) -> WorkflowDecision:
        """Validate exact graph and policy references before persistence."""

        graph = self._graphs.get(command.workflow_ref)
        if graph is None:
            return WorkflowDecision(accepted=False, reason="workflow-version-unknown")
        references = (
            command.execution_policy_ref,
            command.gate_policy_ref,
            command.evidence_policy_ref,
        )
        digests = (
            command.workflow_digest,
            command.execution_policy_digest,
            command.gate_policy_digest,
            command.evidence_policy_digest,
        )
        exact_refs = (
            graph.execution_policy_ref == command.execution_policy_ref
            and graph.gate_policy_ref == command.gate_policy_ref
        )
        exact_policy_digests = all(
            self._policy_digests.get(reference) == digest
            for reference, digest in zip(references, digests[1:], strict=True)
        )
        if (
            command.workflow_digest != graph.digest
            or not exact_refs
            or not exact_policy_digests
            or any(_VERSIONED_REFERENCE.fullmatch(value) is None for value in references)
            or any(_SHA256.fullmatch(value) is None for value in digests)
        ):
            return WorkflowDecision(accepted=False, reason="workflow-pin-mismatch")
        activity = next(
            stage.activity_class for stage in graph.stages if stage.key == graph.initial_stage
        )
        return WorkflowDecision(
            accepted=True,
            reason="accepted",
            activity_class=activity,
            initial_stage=graph.initial_stage,
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
        if not snapshot.run_started:
            return WorkflowDecision(accepted=False, reason="run-not-started")
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

    def pins_match(
        self,
        workflow_ref: str,
        workflow_digest: str,
        policy_pins: tuple[tuple[str, str], ...],
    ) -> bool:
        """Verify that persisted immutable pins still match this composed catalog."""

        graph = self._graphs.get(workflow_ref)
        return (
            graph is not None
            and graph.digest == workflow_digest
            and all(
                self._policy_digests.get(reference) == digest for reference, digest in policy_pins
            )
        )


def _digest(payload: dict[str, object]) -> bytes:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).digest()
