"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:9826074d4caf513025306e895b4d8083c8df77751dccd222b940816b853d0f21
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ActivityClass",
    "BootstrapReceipt",
    "BootstrapRequest",
    "CustodyTransferRequest",
    "CustodyTransferredPayload",
    "DurabilityState",
    "EvidenceRequest",
    "FreezeCriteriaRequest",
    "Priority",
    "Problem",
    "ProofCriterion",
    "ProofReceipt",
    "ResolveCloseRequest",
    "SourceReference",
    "TelemetryContext",
    "TicketCommandResult",
    "TicketCreateRequest",
    "TicketCreatedPayload",
    "TicketResource",
    "TimelineEvent",
    "TimelineResponse",
    "VerdictDecision",
    "VerdictRequest",
    "WorkflowReceipt",
    "WorkflowTransitionRequest",
]


class _BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)


class ActivityClass(StrEnum):
    WORK = "work"
    VERIFICATION = "verification"


class BootstrapRequest(_BoundaryModel):
    commander_name: Annotated[str, Field(min_length=1, max_length=120)]
    commander_vault_ref: Annotated[str, Field(pattern="^vault-ref:[a-z0-9/_-]+$")]
    operator_credential_ref: Annotated[str, Field(pattern="^credential-ref:[a-z0-9/_-]+$")]
    operator_name: Annotated[str, Field(min_length=1, max_length=120)]
    operator_vault_ref: Annotated[str, Field(pattern="^vault-ref:[a-z0-9/_-]+$")]
    tenant_name: Annotated[str, Field(min_length=1, max_length=120)]
    tenant_slug: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{1,62}$")]


class CustodyTransferRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1)]
    from_custodian_id: UUID
    protected_transfer: bool
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    to_custodian_id: UUID


class CustodyTransferredPayload(_BoundaryModel):
    from_custodian_id: UUID
    reason: str
    to_custodian_id: UUID


class DurabilityState(StrEnum):
    DURABILITY_PENDING = "durability_pending"


class EvidenceRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1)]
    evidence_id: UUID
    criterion_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    artifact_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    content: Annotated[str, Field(min_length=1, max_length=100000)]


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class Problem(_BoundaryModel):
    code: Literal[
        "bootstrap-consumed",
        "bootstrap-expired",
        "bootstrap-nonempty",
        "bootstrap-origin",
        "idempotency-conflict",
        "proof-candidate-author-mismatch",
        "proof-candidate-digest-invalid",
        "proof-candidate-digest-not-current",
        "proof-candidate-unchanged",
        "proof-criteria-already-frozen",
        "proof-criteria-invalid",
        "proof-criterion-unknown",
        "proof-current-evidence-missing",
        "proof-evidence-digest-mismatch",
        "proof-evidence-id-conflict",
        "proof-protected-authority-required",
        "proof-self-review-refused",
        "proof-verdict-id-conflict",
        "tenant-scope-denied",
        "unauthorized",
        "validation-error",
        "version-conflict",
        "workflow-predicate-unsatisfied",
        "proof-incomplete",
        "workflow-state-conflict",
        "workflow-terminal",
        "workflow-transition-not-declared",
        "workflow-version-unknown",
        "workflow-not-terminal",
    ]
    command_id: UUID | None = None
    current_version: Annotated[int, Field(ge=0)] | None = None
    detail: str
    status: Annotated[int, Field(ge=400, le=599)]
    title: str
    type_uri: str = Field(alias="type", serialization_alias="type")


class ProofCriterion(_BoundaryModel):
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    candidate_dependent: bool
    requires_verdict: bool


class ResolveCloseRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1)]
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]


class SourceReference(_BoundaryModel):
    kind: Annotated[str, Field(min_length=1, max_length=64)]
    ref: Annotated[str, Field(min_length=1, max_length=256)]


class TelemetryContext(_BoundaryModel):
    schema_id: Literal["ctower.telemetry-context/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    trace_id: Annotated[str, Field(pattern="^[a-f0-9]{32}$")]
    span_id: Annotated[str, Field(pattern="^[a-f0-9]{16}$")]
    trace_flags: Annotated[int, Field(ge=0, le=255)]
    trace_state: Annotated[str, Field(max_length=512)] | None = None
    correlation_id: Annotated[str, Field(min_length=1, max_length=128)]
    causation_id: Annotated[str, Field(min_length=1, max_length=128)]
    tenant_id: Annotated[str, Field(min_length=1, max_length=128)]
    actor_id: Annotated[str, Field(min_length=1, max_length=128)]
    command_id: Annotated[str, Field(min_length=1, max_length=128)]
    ticket_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    workflow_run_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    stage_attempt_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    job_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    runner_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    fencing_token: Annotated[int, Field(ge=1)] | None = None
    effect_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    component_revision_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    deployment_id: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class VerdictDecision(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class WorkflowTransitionRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=0)]
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    source_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    destination_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]


class BootstrapReceipt(_BoundaryModel):
    command_id: UUID
    commander_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    operator_id: UUID
    receipt_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    tenant_id: UUID


class FreezeCriteriaRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=0)]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    criteria: Annotated[tuple[ProofCriterion, ...], Field(min_length=1)]


class ProofReceipt(_BoundaryModel):
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    invalidated_evidence_ids: tuple[UUID, ...]
    invalidated_verdict_ids: tuple[UUID, ...]
    proof_id: UUID
    satisfied: bool
    ticket_id: UUID
    version: Annotated[int, Field(ge=1)]


class TicketCreateRequest(_BoundaryModel):
    initial_custodian_id: UUID
    priority: Priority
    source: SourceReference
    title: Annotated[str, Field(min_length=1, max_length=200)]


class TicketCreatedPayload(_BoundaryModel):
    custodian_id: UUID
    priority: Priority
    source_kind: Annotated[str, Field(min_length=1, max_length=64)]
    source_ref: Annotated[str, Field(min_length=1, max_length=256)]
    title: str


class TicketResource(_BoundaryModel):
    created_at: datetime
    custodian_id: UUID
    durability_state: DurabilityState
    priority: Priority
    source: SourceReference
    ticket_id: UUID
    title: str
    version: Annotated[int, Field(ge=1)]


class VerdictRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1)]
    verdict_id: UUID
    criterion_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    decision: VerdictDecision


class WorkflowReceipt(_BoundaryModel):
    activity_class: ActivityClass
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    lifecycle_facts: Annotated[tuple[Literal["resolved", "closed"], ...], Field(max_length=2)]
    stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    ticket_id: UUID
    version: Annotated[int, Field(ge=1)]
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    workflow_run_id: UUID


class TicketCommandResult(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    ticket: TicketResource


class TimelineEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_id: UUID
    kind: Literal["ticket.created", "ticket.custody_transferred"]
    occurred_at: datetime
    payload: TicketCreatedPayload | CustodyTransferredPayload
    sequence: Annotated[int, Field(ge=1)]


class TimelineResponse(_BoundaryModel):
    durability_state: DurabilityState
    events: tuple[TimelineEvent, ...]
    ticket_id: UUID
