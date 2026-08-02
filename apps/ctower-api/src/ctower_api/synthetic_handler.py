"""The fixed four-stage synthetic handler over generated public operations."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from ctower_client import (
    AdmitIntent,
    CtowerClient,
    DurabilityState,
    EvidenceRequest,
    FreezeCriteriaRequest,
    Priority,
    ProofCriterion,
    ResolveCloseRequest,
    SourceReference,
    TicketCreateRequest,
    TicketIntentRequest,
    VerdictDecision,
    VerdictRequest,
    WorkflowStartRequest,
    WorkflowTransitionRequest,
)
from ctower_kernel.runtime import FixedOperationAttempt, FixedOperationCompletion

__all__ = ["SyntheticFourStageHandler", "SyntheticRetryError"]

_NAMESPACE = UUID("7c1232c2-4b7e-5d3b-9d4b-f27b08e8159d")
_WORKFLOW_REF = "ctower.trust-spine-four-stage@1"
_CANDIDATE_DIGEST = "sha256:b879ba3bf322d26bbad51ed14395684607462c74c711529dfb73dfd80c90082d"
_EVIDENCE_DIGEST = "sha256:208e0e34106e007b2efb3882e25ce01a5fb6e7eb77b6cc7d1022ae4f844bf128"
_EVIDENCE = '{"candidate":"v2","criterion":"artifact-current","observed":"pass"}\n'


class SyntheticRetryError(RuntimeError):
    """A committed semantic step still awaits accepted durability."""


@dataclass(frozen=True, slots=True)
class SyntheticPolicyPins:
    workflow_digest: str
    execution_policy_digest: str
    gate_policy_digest: str
    evidence_policy_digest: str


@dataclass(frozen=True, slots=True)
class SyntheticFourStageHandler:
    """Drive one allowlisted sequence with stable per-job command identities."""

    author: CtowerClient
    reviewer: CtowerClient
    author_id: UUID
    pins: SyntheticPolicyPins

    def execute(self, attempt: FixedOperationAttempt) -> FixedOperationCompletion:
        ticket = self.author.create_ticket(
            TicketCreateRequest(
                initial_custodian_id=self.author_id,
                priority=Priority.P1,
                project_key="ctower",
                source=SourceReference(
                    kind="fixture",
                    ref="ctower:i1.6:api-cli-trust-spine",
                ),
                title="Prove the ctower API and CLI trust spine",
            ),
            command_id=_command(attempt, "capture"),
        )
        _accepted(ticket.durability_state)
        ticket_id = ticket.ticket.ticket_id
        self._start_and_frame(attempt, ticket_id)
        self._verify(attempt, ticket_id)
        closed = self.author.resolve_close_workflow(
            ticket_id,
            ResolveCloseRequest(expected_version=4, workflow_ref=_WORKFLOW_REF),
            command_id=_command(attempt, "resolve-close"),
        )
        _accepted(closed.durability_state)
        if closed.lifecycle_facts != ("resolved", "closed"):
            raise RuntimeError("synthetic close omitted exact terminal lifecycle facts")
        return FixedOperationCompletion(
            succeeded=True,
            ticket_id=ticket_id,
            lifecycle_facts=closed.lifecycle_facts,
            detail_code="synthetic-four-stage-complete",
        )

    def _start_and_frame(self, attempt: FixedOperationAttempt, ticket_id: UUID) -> None:
        started = self.author.start_ticket_workflow(
            ticket_id,
            WorkflowStartRequest(
                workflow_ref=_WORKFLOW_REF,
                workflow_digest=self.pins.workflow_digest,
                execution_policy_ref="ctower.trust-spine-four-stage.execution@1",
                execution_policy_digest=self.pins.execution_policy_digest,
                gate_policy_ref="ctower.trust-spine-four-stage.gates@1",
                gate_policy_digest=self.pins.gate_policy_digest,
                evidence_policy_ref="ctower.trust-spine-four-stage.evidence@1",
                evidence_policy_digest=self.pins.evidence_policy_digest,
            ),
            command_id=_command(attempt, "start"),
        )
        _accepted(started.durability_state)
        admitted = self.author.apply_ticket_intent(
            ticket_id,
            TicketIntentRequest(
                intent=AdmitIntent(
                    kind="admit",
                    expected_version=1,
                    reason="Synthetic fixture admission",
                )
            ),
            command_id=_command(attempt, "admit"),
        )
        _accepted(admitted.durability_state)
        framed = self.author.transition_workflow(
            ticket_id,
            WorkflowTransitionRequest(
                expected_version=1,
                workflow_ref=_WORKFLOW_REF,
                source_stage="capture",
                destination_stage="frame",
            ),
            command_id=_command(attempt, "frame"),
        )
        _accepted(framed.durability_state)

    def _verify(self, attempt: FixedOperationAttempt, ticket_id: UUID) -> None:
        frozen = self.author.freeze_proof_criteria(
            ticket_id,
            FreezeCriteriaRequest(
                expected_version=0,
                candidate_digest=_CANDIDATE_DIGEST,
                criteria=(
                    ProofCriterion(
                        key="artifact-current",
                        description="Artifact evidence matches the current candidate.",
                        candidate_dependent=True,
                        requires_verdict=True,
                    ),
                ),
            ),
            command_id=_command(attempt, "freeze"),
        )
        _accepted(frozen.durability_state)
        verifying = self.author.transition_workflow(
            ticket_id,
            WorkflowTransitionRequest(
                expected_version=2,
                workflow_ref=_WORKFLOW_REF,
                source_stage="frame",
                destination_stage="verify",
            ),
            command_id=_command(attempt, "verify"),
        )
        _accepted(verifying.durability_state)
        evidence = self.author.record_proof_evidence(
            ticket_id,
            EvidenceRequest(
                expected_version=1,
                evidence_id=_identity(attempt, "evidence"),
                criterion_key="artifact-current",
                candidate_digest=_CANDIDATE_DIGEST,
                artifact_digest=_EVIDENCE_DIGEST,
                content=_EVIDENCE,
            ),
            command_id=_command(attempt, "evidence"),
        )
        _accepted(evidence.durability_state)
        verdict = self.reviewer.record_proof_verdict(
            ticket_id,
            VerdictRequest(
                expected_version=2,
                verdict_id=_identity(attempt, "verdict"),
                criterion_key="artifact-current",
                candidate_digest=_CANDIDATE_DIGEST,
                decision=VerdictDecision.PASS,
            ),
            command_id=_command(attempt, "verdict"),
        )
        _accepted(verdict.durability_state)
        closing = self.author.transition_workflow(
            ticket_id,
            WorkflowTransitionRequest(
                expected_version=3,
                workflow_ref=_WORKFLOW_REF,
                source_stage="verify",
                destination_stage="close",
            ),
            command_id=_command(attempt, "close"),
        )
        _accepted(closing.durability_state)


def _command(attempt: FixedOperationAttempt, step: str) -> UUID:
    return uuid5(_NAMESPACE, f"ctower:i1.6:synthetic:{attempt.job.job_id}:command:{step}")


def _identity(attempt: FixedOperationAttempt, name: str) -> UUID:
    return uuid5(_NAMESPACE, f"ctower:i1.6:synthetic:{attempt.job.job_id}:{name}")


def _accepted(state: DurabilityState) -> None:
    if state is not DurabilityState.ACCEPTED:
        raise SyntheticRetryError("synthetic semantic step awaits accepted durability")
