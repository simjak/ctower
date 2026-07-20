"""Immutable proof-policy decisions over supplied facts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID

from ctower_kernel.telemetry import TelemetryContext

if TYPE_CHECKING:
    from ctower_kernel.record import RecordProblem

__all__ = [
    "ChangeCandidate",
    "Criterion",
    "Evidence",
    "FreezeCriteria",
    "Proof",
    "ProofActor",
    "ProofDecision",
    "ProofMutation",
    "ProofReceipt",
    "ProofSnapshot",
    "RecordEvidence",
    "RecordVerdict",
    "Verdict",
    "VerdictDecision",
]

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_KEY = re.compile(r"^[a-z][a-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class ProofActor:
    """Minimal authenticated authority facts used by proof policy."""

    principal_id: UUID
    tenant_id: UUID
    kind: Literal["operator", "commander"]


@dataclass(frozen=True, slots=True)
class Criterion:
    """One immutable acceptance obligation."""

    key: str
    description: str
    candidate_dependent: bool
    requires_verdict: bool

    def __post_init__(self) -> None:
        if _KEY.fullmatch(self.key) is None:
            raise ValueError("criterion key must be stable")
        if not self.description:
            raise ValueError("criterion description must be nonempty")


@dataclass(frozen=True, slots=True)
class Evidence:
    """One content-addressed artifact bound to a candidate."""

    evidence_id: UUID
    criterion_key: str
    candidate_digest: str
    artifact_digest: str
    producer_id: UUID


class VerdictDecision(StrEnum):
    """Protected review outcome."""

    PASSING = "pass"
    FAILING = "fail"


@dataclass(frozen=True, slots=True)
class Verdict:
    """One protected review fact."""

    verdict_id: UUID
    criterion_key: str
    candidate_digest: str
    reviewer_id: UUID
    decision: VerdictDecision


@dataclass(frozen=True, slots=True)
class ProofSnapshot:
    """Immutable current proof facts supplied to a decision."""

    criteria: tuple[Criterion, ...]
    candidate_digest: str | None
    candidate_author_id: UUID | None
    evidence: tuple[Evidence, ...]
    verdicts: tuple[Verdict, ...]
    invalidated_evidence_ids: frozenset[UUID]
    invalidated_verdict_ids: frozenset[UUID]

    @classmethod
    def empty(cls) -> ProofSnapshot:
        """Construct the only legal pre-freeze state."""

        return cls(
            criteria=(),
            candidate_digest=None,
            candidate_author_id=None,
            evidence=(),
            verdicts=(),
            invalidated_evidence_ids=frozenset(),
            invalidated_verdict_ids=frozenset(),
        )


@dataclass(frozen=True, slots=True)
class FreezeCriteria:
    """Freeze criteria and the initial candidate identity together."""

    candidate_digest: str
    candidate_author_id: UUID
    criteria: tuple[Criterion, ...]


@dataclass(frozen=True, slots=True)
class RecordEvidence:
    """Attach verified bytes to one frozen criterion."""

    evidence_id: UUID
    criterion_key: str
    candidate_digest: str
    artifact_digest: str
    content: bytes


@dataclass(frozen=True, slots=True)
class RecordVerdict:
    """Apply protected independent review to current evidence."""

    verdict_id: UUID
    criterion_key: str
    candidate_digest: str
    decision: VerdictDecision


@dataclass(frozen=True, slots=True)
class ChangeCandidate:
    """Declare a new candidate digest and invalidate dependent proof."""

    candidate_digest: str


type ProofCommand = FreezeCriteria | RecordEvidence | RecordVerdict | ChangeCandidate


@dataclass(frozen=True, slots=True)
class ProofMutation:
    """Version-checked envelope for one proof command."""

    client_command_id: UUID
    ticket_id: UUID
    expected_version: int
    command: ProofCommand

    def request_payload(self) -> dict[str, object]:
        """Return the complete idempotency payload."""

        return {
            "ticket_id": str(self.ticket_id),
            "expected_version": self.expected_version,
            "command": _command_payload(self.command),
        }


@dataclass(frozen=True, slots=True)
class ProofReceipt:
    """Committed proof state retained for exact replay."""

    command_id: UUID
    event_ids: tuple[UUID, ...]
    proof_id: UUID
    ticket_id: UUID
    version: int
    candidate_digest: str
    satisfied: bool
    invalidated_evidence_ids: tuple[UUID, ...] = ()
    invalidated_verdict_ids: tuple[UUID, ...] = ()

    def response_payload(self) -> dict[str, object]:
        """Return the stable public command receipt."""

        return {
            "candidate_digest": self.candidate_digest,
            "command_id": str(self.command_id),
            "durability_state": "durability_pending",
            "event_ids": [str(item) for item in self.event_ids],
            "invalidated_evidence_ids": [str(item) for item in self.invalidated_evidence_ids],
            "invalidated_verdict_ids": [str(item) for item in self.invalidated_verdict_ids],
            "proof_id": str(self.proof_id),
            "satisfied": self.satisfied,
            "ticket_id": str(self.ticket_id),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ProofDecision:
    """A fail-closed result and the facts it would append."""

    accepted: bool
    reason: str
    snapshot: ProofSnapshot
    facts: tuple[str, ...] = ()
    invalidated_evidence_ids: tuple[UUID, ...] = ()
    invalidated_verdict_ids: tuple[UUID, ...] = ()


class _ProofWriter(Protocol):
    def mutate_proof(
        self,
        evaluator: Proof,
        actor: ProofActor,
        mutation: ProofMutation,
        *,
        request_digest: bytes,
        now: datetime,
        telemetry: TelemetryContext,
    ) -> ProofReceipt | RecordProblem: ...


class Proof:
    """Decide proof mutations without storage or transport dependencies."""

    def __init__(
        self,
        *,
        writer: _ProofWriter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._writer = writer
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        actor: ProofActor,
        mutation: ProofMutation,
        *,
        telemetry: TelemetryContext,
    ) -> ProofReceipt | RecordProblem:
        """Commit or exactly replay one version-checked proof mutation."""

        if self._writer is None:
            raise RuntimeError("proof persistence is not configured")
        request_digest = hashlib.sha256(_canonical_json(mutation.request_payload())).digest()
        return self._writer.mutate_proof(
            self,
            actor,
            mutation,
            request_digest=request_digest,
            now=self._clock(),
            telemetry=telemetry,
        )

    def decide(
        self,
        actor: ProofActor,
        snapshot: ProofSnapshot,
        command: ProofCommand,
    ) -> ProofDecision:
        """Decide one immutable proof command."""

        if isinstance(command, RecordEvidence):
            return self._record_evidence(actor, snapshot, command)
        if isinstance(command, RecordVerdict):
            return self._record_verdict(actor, snapshot, command)
        if isinstance(command, ChangeCandidate):
            return self._change_candidate(actor, snapshot, command)
        return self._freeze_criteria(actor, snapshot, command)

    def is_satisfied(self, snapshot: ProofSnapshot) -> bool:
        """Require current evidence and every configured protected verdict."""

        if not snapshot.criteria or snapshot.candidate_digest is None:
            return False
        return all(
            self._criterion_satisfied(snapshot, criterion) for criterion in snapshot.criteria
        )

    def _freeze_criteria(
        self, actor: ProofActor, snapshot: ProofSnapshot, command: FreezeCriteria
    ) -> ProofDecision:
        if snapshot.criteria:
            return ProofDecision(
                accepted=False,
                reason="criteria-already-frozen",
                snapshot=snapshot,
            )
        if actor.principal_id != command.candidate_author_id:
            return ProofDecision(
                accepted=False,
                reason="candidate-author-mismatch",
                snapshot=snapshot,
            )
        if not command.criteria or len({item.key for item in command.criteria}) != len(
            command.criteria
        ):
            return ProofDecision(
                accepted=False,
                reason="criteria-invalid",
                snapshot=snapshot,
            )
        if _DIGEST.fullmatch(command.candidate_digest) is None:
            return ProofDecision(
                accepted=False,
                reason="candidate-digest-invalid",
                snapshot=snapshot,
            )
        return ProofDecision(
            accepted=True,
            reason="accepted",
            snapshot=replace(
                snapshot,
                criteria=command.criteria,
                candidate_digest=command.candidate_digest,
                candidate_author_id=command.candidate_author_id,
            ),
            facts=("criteria.frozen",),
        )

    def _record_evidence(
        self, actor: ProofActor, snapshot: ProofSnapshot, command: RecordEvidence
    ) -> ProofDecision:
        if command.candidate_digest != snapshot.candidate_digest:
            return _refusal("candidate-digest-not-current", snapshot)
        criterion = next(
            (item for item in snapshot.criteria if item.key == command.criterion_key), None
        )
        if criterion is None:
            return _refusal("criterion-unknown", snapshot)
        actual_digest = "sha256:" + hashlib.sha256(command.content).hexdigest()
        if actual_digest != command.artifact_digest:
            return _refusal("evidence-digest-mismatch", snapshot)
        if any(item.evidence_id == command.evidence_id for item in snapshot.evidence):
            return _refusal("evidence-id-conflict", snapshot)
        evidence = Evidence(
            evidence_id=command.evidence_id,
            criterion_key=criterion.key,
            candidate_digest=command.candidate_digest,
            artifact_digest=command.artifact_digest,
            producer_id=actor.principal_id,
        )
        return ProofDecision(
            accepted=True,
            reason="accepted",
            snapshot=replace(snapshot, evidence=(*snapshot.evidence, evidence)),
            facts=("evidence.recorded",),
        )

    def _record_verdict(
        self, actor: ProofActor, snapshot: ProofSnapshot, command: RecordVerdict
    ) -> ProofDecision:
        if actor.principal_id == snapshot.candidate_author_id:
            return _refusal("self-review-refused", snapshot)
        if actor.kind != "operator":
            return _refusal("protected-authority-required", snapshot)
        if command.candidate_digest != snapshot.candidate_digest:
            return _refusal("candidate-digest-not-current", snapshot)
        if not any(
            item.criterion_key == command.criterion_key
            and item.candidate_digest == snapshot.candidate_digest
            for item in snapshot.evidence
        ):
            return _refusal("current-evidence-missing", snapshot)
        if any(item.verdict_id == command.verdict_id for item in snapshot.verdicts):
            return _refusal("verdict-id-conflict", snapshot)
        verdict = Verdict(
            verdict_id=command.verdict_id,
            criterion_key=command.criterion_key,
            candidate_digest=command.candidate_digest,
            reviewer_id=actor.principal_id,
            decision=command.decision,
        )
        return ProofDecision(
            accepted=True,
            reason="accepted",
            snapshot=replace(snapshot, verdicts=(*snapshot.verdicts, verdict)),
            facts=("verdict.recorded",),
        )

    def _change_candidate(
        self, actor: ProofActor, snapshot: ProofSnapshot, command: ChangeCandidate
    ) -> ProofDecision:
        if actor.principal_id != snapshot.candidate_author_id:
            return _refusal("candidate-author-mismatch", snapshot)
        if _DIGEST.fullmatch(command.candidate_digest) is None:
            return _refusal("candidate-digest-invalid", snapshot)
        if command.candidate_digest == snapshot.candidate_digest:
            return _refusal("candidate-unchanged", snapshot)
        dependent_keys = {item.key for item in snapshot.criteria if item.candidate_dependent}
        evidence_ids = tuple(
            item.evidence_id
            for item in snapshot.evidence
            if item.criterion_key in dependent_keys
            and item.evidence_id not in snapshot.invalidated_evidence_ids
        )
        verdict_ids = tuple(
            item.verdict_id
            for item in snapshot.verdicts
            if item.criterion_key in dependent_keys
            and item.verdict_id not in snapshot.invalidated_verdict_ids
        )
        next_snapshot = replace(
            snapshot,
            candidate_digest=command.candidate_digest,
            invalidated_evidence_ids=(snapshot.invalidated_evidence_ids | frozenset(evidence_ids)),
            invalidated_verdict_ids=(snapshot.invalidated_verdict_ids | frozenset(verdict_ids)),
        )
        return ProofDecision(
            accepted=True,
            reason="accepted",
            snapshot=next_snapshot,
            facts=("candidate.changed", "dependent-proof.invalidated"),
            invalidated_evidence_ids=evidence_ids,
            invalidated_verdict_ids=verdict_ids,
        )

    @staticmethod
    def _criterion_satisfied(snapshot: ProofSnapshot, criterion: Criterion) -> bool:
        if not Proof._has_current_evidence(snapshot, criterion):
            return False
        return not criterion.requires_verdict or Proof._has_passing_verdict(snapshot, criterion)

    @staticmethod
    def _has_current_evidence(snapshot: ProofSnapshot, criterion: Criterion) -> bool:
        return any(
            item.criterion_key == criterion.key
            and item.evidence_id not in snapshot.invalidated_evidence_ids
            and (
                not criterion.candidate_dependent
                or item.candidate_digest == snapshot.candidate_digest
            )
            for item in snapshot.evidence
        )

    @staticmethod
    def _has_passing_verdict(snapshot: ProofSnapshot, criterion: Criterion) -> bool:
        applicable = tuple(
            item
            for item in snapshot.verdicts
            if item.criterion_key == criterion.key
            and item.verdict_id not in snapshot.invalidated_verdict_ids
            and (
                not criterion.candidate_dependent
                or item.candidate_digest == snapshot.candidate_digest
            )
        )
        return bool(applicable) and applicable[-1].decision is VerdictDecision.PASSING


def _refusal(reason: str, snapshot: ProofSnapshot) -> ProofDecision:
    return ProofDecision(accepted=False, reason=reason, snapshot=snapshot)


def _command_payload(command: ProofCommand) -> dict[str, object]:
    if isinstance(command, FreezeCriteria):
        return {
            "kind": "freeze_criteria",
            "candidate_digest": command.candidate_digest,
            "candidate_author_id": str(command.candidate_author_id),
            "criteria": [
                {
                    "key": item.key,
                    "description": item.description,
                    "candidate_dependent": item.candidate_dependent,
                    "requires_verdict": item.requires_verdict,
                }
                for item in command.criteria
            ],
        }
    if isinstance(command, RecordEvidence):
        return {
            "kind": "record_evidence",
            "evidence_id": str(command.evidence_id),
            "criterion_key": command.criterion_key,
            "candidate_digest": command.candidate_digest,
            "artifact_digest": command.artifact_digest,
            "content_hex": command.content.hex(),
        }
    if isinstance(command, RecordVerdict):
        return {
            "kind": "record_verdict",
            "verdict_id": str(command.verdict_id),
            "criterion_key": command.criterion_key,
            "candidate_digest": command.candidate_digest,
            "decision": command.decision.value,
        }
    return {"kind": "change_candidate", "candidate_digest": command.candidate_digest}


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
