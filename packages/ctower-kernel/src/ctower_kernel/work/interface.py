"""Deep Work Module for ticket policy and authoritative commands."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from ctower_kernel.record import (
    Actor,
    CustodyCommand,
    PrincipalKind,
    Record,
    RecordProblem,
    TicketCommand,
    TicketCommandResult,
)
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext
from ctower_kernel.work._custody_policy import initial_custody_refusal
from ctower_kernel.work._scheduling import schedule

__all__ = [
    "AddRelation",
    "Admit",
    "AssignmentInterval",
    "AssignmentKind",
    "Block",
    "ChangeAssignment",
    "ChangePriority",
    "Defer",
    "RelationKind",
    "Reopen",
    "SchedulingCandidate",
    "SchedulingDecision",
    "Unblock",
    "Work",
    "WorkCommand",
    "WorkReadiness",
    "WorkReceipt",
]

PRIORITIES = frozenset({"P0", "P1", "P2"})
MAX_REASON_LENGTH = 500


class AssignmentKind(StrEnum):
    """Orthogonal assignment lanes; only three are mutable through Work.execute."""

    TICKET_CUSTODIAN = "ticket_custodian"
    CURRENT_ASSIGNEE = "current_assignee"
    STAGE_OWNER = "stage_owner"
    REVIEWER_ASSIGNMENT = "reviewer_assignment"
    RUNNER_LEASE_OWNER = "runner_lease_owner"


class RelationKind(StrEnum):
    """Authored ticket-edge vocabulary."""

    PARENT_OF = "parent_of"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    DUPLICATES = "duplicates"
    RELATES_TO = "relates_to"
    CAUSED_BY = "caused_by"


@dataclass(frozen=True, slots=True)
class WorkMutation:
    """Fields common to version-checked authoritative Work commands."""

    client_command_id: UUID
    ticket_id: UUID
    expected_version: int
    reason: str

    def _payload(self, kind: str) -> dict[str, object]:
        return {
            "expected_version": self.expected_version,
            "kind": kind,
            "reason": self.reason,
            "ticket_id": str(self.ticket_id),
        }


@dataclass(frozen=True, slots=True)
class ChangePriority(WorkMutation):
    priority: str
    urgent_evidence_ref: str | None = None

    def request_payload(self) -> dict[str, object]:
        return {
            **self._payload("change_priority"),
            "priority": self.priority,
            "urgent_evidence_ref": self.urgent_evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class ChangeAssignment(WorkMutation):
    assignment_kind: AssignmentKind
    to_principal_id: UUID
    scope_ref: str | None = None

    def request_payload(self) -> dict[str, object]:
        return {
            **self._payload("change_assignment"),
            "assignment_kind": self.assignment_kind.value,
            "scope_ref": self.scope_ref,
            "to_principal_id": str(self.to_principal_id),
        }


@dataclass(frozen=True, slots=True)
class Admit(WorkMutation):
    def request_payload(self) -> dict[str, object]:
        return self._payload("admit")


@dataclass(frozen=True, slots=True)
class Defer(WorkMutation):
    review_after: datetime

    def request_payload(self) -> dict[str, object]:
        return {**self._payload("defer"), "review_after": self.review_after.isoformat()}


@dataclass(frozen=True, slots=True)
class Block(WorkMutation):
    blocker_id: UUID
    blocker_kind: str
    reason_class: str
    owner_principal_id: UUID
    source_ref: str
    affected_stage: str | None
    resolution_condition: str
    next_check_at: datetime | None
    dependency_ref: str | None
    board_impact: bool

    def request_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("client_command_id")
        payload.update(self._payload("block"))
        for field in ("blocker_id", "owner_principal_id"):
            payload[field] = str(payload[field])
        for field in ("next_check_at",):
            value = payload[field]
            payload[field] = value.isoformat() if isinstance(value, datetime) else None
        return payload


@dataclass(frozen=True, slots=True)
class Unblock(WorkMutation):
    blocker_id: UUID
    resolution_evidence_ref: str

    def request_payload(self) -> dict[str, object]:
        return {
            **self._payload("unblock"),
            "blocker_id": str(self.blocker_id),
            "resolution_evidence_ref": self.resolution_evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class Reopen(WorkMutation):
    priority_policy: str = "carry_forward"

    def request_payload(self) -> dict[str, object]:
        return {**self._payload("reopen"), "priority_policy": self.priority_policy}


@dataclass(frozen=True, slots=True)
class AddRelation(WorkMutation):
    relation_kind: RelationKind
    target_ticket_id: UUID

    def request_payload(self) -> dict[str, object]:
        return {
            **self._payload("add_relation"),
            "relation_kind": self.relation_kind.value,
            "target_ticket_id": str(self.target_ticket_id),
        }


type WorkCommand = (
    ChangePriority | ChangeAssignment | Admit | Defer | Block | Unblock | Reopen | AddRelation
)


@dataclass(frozen=True, slots=True)
class WorkReceipt:
    command_id: UUID
    event_ids: tuple[UUID, ...]
    operation: str
    ticket_id: UUID
    version: int

    def response_payload(self) -> dict[str, object]:
        return {
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "operation": self.operation,
            "ticket_id": str(self.ticket_id),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class AssignmentInterval:
    assignment_kind: AssignmentKind
    episode_number: int
    principal_id: UUID
    assigned_at: datetime
    released_at: datetime | None
    changed_by: UUID
    reason: str
    scope_ref: str | None
    sequence: int

    def response_payload(self) -> dict[str, object]:
        return {
            "assigned_at": self.assigned_at.isoformat(),
            "assignment_kind": self.assignment_kind.value,
            "changed_by": str(self.changed_by),
            "episode_number": self.episode_number,
            "principal_id": str(self.principal_id),
            "reason": self.reason,
            "released_at": self.released_at.isoformat() if self.released_at else None,
            "scope_ref": self.scope_ref,
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class WorkReadiness:
    ready: bool
    unmet_facts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SchedulingCandidate:
    """Restart-stable scheduling facts evaluated only at a dispatch checkpoint."""

    ticket_id: UUID
    priority: str
    eligible_since: datetime
    unmet_eligibility: tuple[str, ...] = ()
    checkpoint_verified: bool = False


@dataclass(frozen=True, slots=True)
class SchedulingDecision:
    """Deterministic eligible order plus explicit hard-gate exclusions."""

    ordered_ticket_ids: tuple[UUID, ...]
    excluded_ticket_ids: tuple[UUID, ...]
    checkpoint_preemptible_ids: tuple[UUID, ...]


class _WorkWriter(Protocol):
    def execute_work(
        self,
        actor: Actor,
        command: WorkCommand,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> WorkReceipt | RecordProblem: ...

    def assignments(
        self, actor: Actor, ticket_id: UUID
    ) -> tuple[AssignmentInterval, ...] | RecordProblem: ...

    def readiness(self, actor: Actor, ticket_id: UUID) -> WorkReadiness | RecordProblem: ...


class Work:
    """Own ticket command policy while Record owns atomic persistence."""

    def __init__(
        self,
        record: Record,
        *,
        writer: _WorkWriter | None = None,
        clock: Callable[[], datetime] | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self._record = record
        self._writer = writer
        self._clock = clock or (lambda: datetime.now(UTC))
        self._telemetry = telemetry or NoopTelemetry()

    def create_ticket(
        self, actor: Actor, command: TicketCommand, *, telemetry: TelemetryContext
    ) -> TicketCommandResult | RecordProblem:
        """Enforce priority policy before appending a ticket."""

        if actor.kind is PrincipalKind.MIGRATION_IMPORTER:
            return _importer_refusal(command.client_command_id)
        custody_refusal = initial_custody_refusal(
            actor,
            command.client_command_id,
            command.initial_custodian_id,
        )
        if custody_refusal is not None:
            request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
            outcome = self._record.create_ticket(
                actor,
                command,
                request_digest=request_digest,
                policy_refusal=custody_refusal,
                now=self._clock(),
                telemetry=telemetry,
            )
            self._emit("work.create_ticket", telemetry, outcome)
            return outcome
        if command.priority not in PRIORITIES:
            return _refusal(command, "Ticket priority is outside P0/P1/P2.")
        if command.priority == "P0" and actor.kind is not PrincipalKind.OPERATOR:
            return _refusal(command, "Only an operator may create a P0 ticket.")
        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        outcome = self._record.create_ticket(
            actor,
            command,
            request_digest=request_digest,
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("work.create_ticket", telemetry, outcome)
        return outcome

    def transfer_custody(
        self, actor: Actor, command: CustodyCommand, *, telemetry: TelemetryContext
    ) -> TicketCommandResult | RecordProblem:
        """Require protected operator authority before transferring custody."""

        if actor.kind is PrincipalKind.MIGRATION_IMPORTER:
            return _importer_refusal(command.client_command_id)
        if actor.kind is not PrincipalKind.OPERATOR or not command.protected_transfer:
            return RecordProblem(
                code="unauthorized",
                detail="Custody transfer requires protected operator authority.",
                status=403,
                title="Custody transfer refused",
                command_id=command.client_command_id,
            )
        request_digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        outcome = self._record.transfer_custody(
            actor,
            command,
            request_digest=request_digest,
            now=self._clock(),
            telemetry=telemetry,
        )
        self._emit("work.transfer_custody", telemetry, outcome)
        return outcome

    def execute(
        self, actor: Actor, command: WorkCommand, *, telemetry: TelemetryContext
    ) -> WorkReceipt | RecordProblem:
        """Authorize and commit one typed Work mutation."""

        refusal = _work_refusal(actor, command)
        if refusal is not None:
            return refusal
        if self._writer is None:
            raise RuntimeError("Work persistence is not configured")
        digest = hashlib.sha256(_canonical_json(command.request_payload())).digest()
        outcome = self._writer.execute_work(
            actor,
            command,
            request_digest=digest,
            now=self._clock(),
            telemetry=telemetry,
        )
        self._telemetry.emit(
            "work.execute",
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )
        return outcome

    def assignments(
        self, actor: Actor, ticket_id: UUID
    ) -> tuple[AssignmentInterval, ...] | RecordProblem:
        """Return tenant-scoped assignment interval history."""

        if actor.kind is PrincipalKind.MIGRATION_IMPORTER:
            return _importer_refusal()
        if self._writer is None:
            raise RuntimeError("Work persistence is not configured")
        return self._writer.assignments(actor, ticket_id)

    def readiness(self, actor: Actor, ticket_id: UUID) -> WorkReadiness | RecordProblem:
        """Return the immutable admission/blocker observation consumed by Workflow."""

        if actor.kind is PrincipalKind.MIGRATION_IMPORTER:
            return _importer_refusal()
        if self._writer is None:
            raise RuntimeError("Work persistence is not configured")
        return self._writer.readiness(actor, ticket_id)

    def schedule(
        self, candidates: tuple[SchedulingCandidate, ...], *, now: datetime
    ) -> SchedulingDecision:
        """Order hard-eligible work with the authored bounded-aging policy."""

        ordered, excluded, preemptible = schedule(candidates, now=now)
        return SchedulingDecision(ordered, excluded, preemptible)

    def _emit(
        self,
        name: str,
        telemetry: TelemetryContext,
        outcome: TicketCommandResult | RecordProblem,
    ) -> None:
        self._telemetry.emit(
            name,
            telemetry,
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=outcome.code if isinstance(outcome, RecordProblem) else "committed",
        )


def _refusal(command: TicketCommand, detail: str) -> RecordProblem:
    return RecordProblem(
        code="unauthorized",
        detail=detail,
        status=403,
        title="Ticket command refused",
        command_id=command.client_command_id,
    )


def _work_refusal(actor: Actor, command: WorkCommand) -> RecordProblem | None:
    if actor.kind is PrincipalKind.MIGRATION_IMPORTER:
        return _importer_refusal(command.client_command_id)
    if (
        command.expected_version < 1
        or not command.reason
        or len(command.reason) > MAX_REASON_LENGTH
    ):
        return _work_problem(command, "validation-error", 422, "Invalid Work command")
    if isinstance(command, ChangePriority):
        priority_refusal = _priority_refusal(actor, command)
        if priority_refusal is not None:
            return priority_refusal
    if isinstance(command, ChangeAssignment):
        return _assignment_refusal(command)
    if isinstance(command, Reopen) and command.priority_policy != "carry_forward":
        return _work_problem(command, "validation-error", 422, "Unsupported priority policy")
    return None


def _importer_refusal(command_id: UUID | None = None) -> RecordProblem:
    return RecordProblem(
        code="migration-capability-denied",
        detail="The migration importer has no general Work authority.",
        status=403,
        title="Migration capability denied",
        command_id=command_id,
    )


def _assignment_refusal(command: ChangeAssignment) -> RecordProblem | None:
    if command.assignment_kind in {
        AssignmentKind.TICKET_CUSTODIAN,
        AssignmentKind.RUNNER_LEASE_OWNER,
    }:
        return _work_problem(
            command,
            "work-assignment-kind-refused",
            409,
            "Protected assignment kind requires its owning Interface",
        )
    if command.assignment_kind is AssignmentKind.CURRENT_ASSIGNEE and command.scope_ref is not None:
        return _work_problem(command, "validation-error", 422, "Current assignee is ticket-scoped")
    return None


def _priority_refusal(actor: Actor, command: ChangePriority) -> RecordProblem | None:
    if command.priority not in PRIORITIES:
        return _work_problem(command, "validation-error", 422, "Invalid priority")
    if actor.kind not in {PrincipalKind.COMMANDER, PrincipalKind.OPERATOR}:
        return _work_problem(
            command, "unauthorized", 403, "Priority change requires task authority"
        )
    if command.priority == "P0" and actor.kind is not PrincipalKind.OPERATOR:
        return _work_problem(command, "unauthorized", 403, "P0 requires operator authority")
    return None


def _work_problem(command: WorkMutation, code: str, status: int, title: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=command.client_command_id,
    )


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
