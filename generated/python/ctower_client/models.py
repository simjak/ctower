"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:f1a3a71dcae091a1146eb825b1a62b96c31e71ed45c9462f342e4c4cca647c83
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ActivityClass",
    "AdmitIntent",
    "AdmittedAuditData",
    "AssignmentChangeRequest",
    "AssignmentChangedAuditData",
    "AssignmentInterval",
    "AssignmentKind",
    "AssignmentList",
    "AuditEvent",
    "AuditPage",
    "BlockIntent",
    "BlockerOpenedAuditData",
    "BlockerResolvedAuditData",
    "BoardCard",
    "BoardLane",
    "BoardView",
    "BootstrapReceipt",
    "BootstrapRequest",
    "CustodyTransferRequest",
    "CustodyTransferredAuditEvent",
    "CustodyTransferredPayload",
    "DeferIntent",
    "DeferredAuditData",
    "DurabilityState",
    "EvidenceRequest",
    "FreezeCriteriaRequest",
    "MutableAssignmentKind",
    "Priority",
    "PriorityChangeRequest",
    "PriorityChangedAuditData",
    "Problem",
    "ProjectionHealth",
    "ProofChangedAuditEvent",
    "ProofChangedAuditPayload",
    "ProofCriterion",
    "ProofReceipt",
    "RelationAddedAuditData",
    "RelationKind",
    "RelationRequest",
    "ReopenIntent",
    "ReopenedAuditData",
    "ResolveCloseRequest",
    "SourceReference",
    "TelemetryContext",
    "TicketCommandResult",
    "TicketCreateRequest",
    "TicketCreatedAuditEvent",
    "TicketCreatedPayload",
    "TicketIntentRequest",
    "TicketResource",
    "TimelineEvent",
    "TimelineResponse",
    "UnblockIntent",
    "VerdictDecision",
    "VerdictRequest",
    "WorkAdmittedAuditPayload",
    "WorkAssignmentChangedAuditPayload",
    "WorkBlockerOpenedAuditPayload",
    "WorkBlockerResolvedAuditPayload",
    "WorkChangedAuditEvent",
    "WorkChangedAuditPayload",
    "WorkDeferredAuditPayload",
    "WorkPriorityChangedAuditPayload",
    "WorkReceipt",
    "WorkRelationAddedAuditPayload",
    "WorkReopenedAuditPayload",
    "WorkflowChangedAuditEvent",
    "WorkflowChangedAuditPayload",
    "WorkflowReceipt",
    "WorkflowStartRequest",
    "WorkflowTransitionRequest",
]


class _BoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True, strict=True)


class ActivityClass(StrEnum):
    WORK = "work"
    VERIFICATION = "verification"


class AdmitIntent(_BoundaryModel):
    kind: Literal["admit"]
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class AdmittedAuditData(_BoundaryModel):
    episode_number: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class AssignmentChangedAuditData(_BoundaryModel):
    assignment_kind: Literal["current_assignee", "stage_owner", "reviewer_assignment"]
    from_principal_id: UUID | None
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    scope_ref: Annotated[str, Field(min_length=1, max_length=256)] | None
    to_principal_id: UUID


class AssignmentKind(StrEnum):
    TICKET_CUSTODIAN = "ticket_custodian"
    CURRENT_ASSIGNEE = "current_assignee"
    STAGE_OWNER = "stage_owner"
    REVIEWER_ASSIGNMENT = "reviewer_assignment"
    RUNNER_LEASE_OWNER = "runner_lease_owner"


class BlockIntent(_BoundaryModel):
    kind: Literal["block"]
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    blocker_id: UUID
    blocker_kind: Literal["dependency", "operator_action", "policy", "resource", "technical"]
    reason_class: Annotated[str, Field(min_length=1, max_length=64)]
    owner_principal_id: UUID
    source_ref: Annotated[str, Field(min_length=1, max_length=256)]
    affected_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")] | None
    resolution_condition: Annotated[str, Field(min_length=1, max_length=500)]
    next_check_at: datetime | None
    dependency_ref: Annotated[str, Field(max_length=256)] | None
    board_impact: bool


class BlockerOpenedAuditData(_BoundaryModel):
    blocker_id: UUID
    board_impact: bool
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class BlockerResolvedAuditData(_BoundaryModel):
    blocker_id: UUID
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    resolution_evidence_ref: Annotated[str, Field(min_length=1, max_length=256)]


class BoardLane(StrEnum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    COMPLETE = "complete"


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


class DeferIntent(_BoundaryModel):
    kind: Literal["defer"]
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    review_after: datetime


class DeferredAuditData(_BoundaryModel):
    episode_number: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    review_after: datetime


class DurabilityState(StrEnum):
    DURABILITY_PENDING = "durability_pending"
    ACCEPTED = "accepted"


class EvidenceRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1)]
    evidence_id: UUID
    criterion_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    artifact_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    content: Annotated[str, Field(min_length=1, max_length=100000)]


class MutableAssignmentKind(StrEnum):
    CURRENT_ASSIGNEE = "current_assignee"
    STAGE_OWNER = "stage_owner"
    REVIEWER_ASSIGNMENT = "reviewer_assignment"


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
        "durability_pending",
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
        "work-assignment-kind-refused",
        "work-assignment-target-ineligible",
        "work-assignment-unchanged",
        "work-priority-unchanged",
        "work-blocker-already-resolved",
        "work-blocker-id-conflict",
        "work-blocker-owner-ineligible",
        "work-blocker-unknown",
        "work-intent-unmet",
        "work-relation-cycle",
        "work-relation-exists",
        "work-reopen-unmet",
        "workflow-already-started",
        "workflow-pin-mismatch",
        "workflow-predicate-unsatisfied",
        "workflow-run-not-started",
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
    unmet_facts: tuple[str, ...] | None = None


class ProjectionHealth(StrEnum):
    CURRENT = "CURRENT"
    STATE_UNKNOWN = "STATE_UNKNOWN"


class ProofChangedAuditPayload(_BoundaryModel):
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    invalidated_evidence_ids: tuple[UUID, ...]
    invalidated_verdict_ids: tuple[UUID, ...]
    operation: Literal["freeze_criteria", "record_evidence", "record_verdict", "change_candidate"]
    proof_version: Annotated[int, Field(ge=1)]
    ticket_id: UUID


class ProofCriterion(_BoundaryModel):
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    description: Annotated[str, Field(min_length=1, max_length=500)]
    candidate_dependent: bool
    requires_verdict: bool


class RelationAddedAuditData(_BoundaryModel):
    relation_kind: Literal["parent_of", "depends_on", "blocks", "duplicates", "relates_to", "caused_by"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    target_ticket_id: UUID


class RelationKind(StrEnum):
    PARENT_OF = "parent_of"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    DUPLICATES = "duplicates"
    RELATES_TO = "relates_to"
    CAUSED_BY = "caused_by"


class ReopenIntent(_BoundaryModel):
    kind: Literal["reopen"]
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    priority_policy: Literal["carry_forward"]


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


class UnblockIntent(_BoundaryModel):
    kind: Literal["unblock"]
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    blocker_id: UUID
    resolution_evidence_ref: Annotated[str, Field(min_length=1, max_length=256)]


class VerdictDecision(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class WorkflowChangedAuditPayload(_BoundaryModel):
    lifecycle_facts: Annotated[tuple[Literal["resolved", "closed"], ...], Field(max_length=2)]
    operation: Literal["start", "transition", "resolve_close"]
    stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    ticket_id: UUID
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    workflow_version: Annotated[int, Field(ge=1)]


class WorkflowStartRequest(_BoundaryModel):
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    workflow_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    execution_policy_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    execution_policy_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    gate_policy_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    gate_policy_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    evidence_policy_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    evidence_policy_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class WorkflowTransitionRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=0)]
    workflow_ref: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*@[1-9][0-9]*$")]
    source_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    destination_stage: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]


class AssignmentChangeRequest(_BoundaryModel):
    assignment_kind: MutableAssignmentKind
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    scope_ref: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    to_principal_id: UUID


class AssignmentInterval(_BoundaryModel):
    assigned_at: datetime
    assignment_kind: AssignmentKind
    changed_by: UUID
    episode_number: Annotated[int, Field(ge=1)]
    principal_id: UUID
    reason: str
    released_at: datetime | None
    scope_ref: str | None
    sequence: Annotated[int, Field(ge=1)]


class BoardCard(_BoundaryModel):
    activity_class: Literal["work", "verification", "None"] | None
    assignee_id: UUID | None
    blocker_opened_at: datetime | None
    blocker_reason: str | None
    custodian_id: UUID
    delivery_facts: tuple[str, ...]
    lane: BoardLane
    priority: Priority
    risk: str | None
    stage_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")] | None
    stage_label: str | None
    ticket_id: UUID
    title: str
    underlying_lane: Literal["backlog", "ready", "in_progress", "in_review", "complete", "None"] | None
    version: Annotated[int, Field(ge=1)]


class BootstrapReceipt(_BoundaryModel):
    command_id: UUID
    commander_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    operator_id: UUID
    receipt_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    tenant_id: UUID


class CustodyTransferredAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["ticket.custody_transferred"]
    occurred_at: datetime
    payload: CustodyTransferredPayload
    record_position: Annotated[int, Field(ge=1)]
    sequence: Annotated[int, Field(ge=1)]
    stream_id: Annotated[str, Field(pattern="^ticket:[0-9a-f-]{36}$")]


class FreezeCriteriaRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=0)]
    candidate_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    criteria: Annotated[tuple[ProofCriterion, ...], Field(min_length=1)]


class PriorityChangeRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1)]
    priority: Priority
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    urgent_evidence_ref: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class PriorityChangedAuditData(_BoundaryModel):
    authority: Literal["commander", "operator"]
    from_priority: Priority
    policy_ref: Literal["ctower.priority-authority@1"]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    to_priority: Priority
    urgent_evidence_ref: Annotated[str, Field(min_length=1, max_length=256)] | None


class ProofChangedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["proof.changed"]
    occurred_at: datetime
    payload: ProofChangedAuditPayload
    record_position: Annotated[int, Field(ge=1)]
    sequence: Annotated[int, Field(ge=1)]
    stream_id: Annotated[str, Field(pattern="^proof:[0-9a-f-]{36}$")]


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


class RelationRequest(_BoundaryModel):
    expected_version: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    relation_kind: RelationKind
    target_ticket_id: UUID


class ReopenedAuditData(_BoundaryModel):
    episode_number: Annotated[int, Field(ge=2)]
    priority: Priority
    reason: Annotated[str, Field(min_length=1, max_length=500)]


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


class TicketIntentRequest(_BoundaryModel):
    intent: AdmitIntent | DeferIntent | BlockIntent | UnblockIntent | ReopenIntent


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


class WorkAdmittedAuditPayload(_BoundaryModel):
    data: AdmittedAuditData
    operation: Literal["admitted"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2)]


class WorkAssignmentChangedAuditPayload(_BoundaryModel):
    data: AssignmentChangedAuditData
    operation: Literal["assignment_changed"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2)]


class WorkBlockerOpenedAuditPayload(_BoundaryModel):
    data: BlockerOpenedAuditData
    operation: Literal["blocker_opened"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2)]


class WorkBlockerResolvedAuditPayload(_BoundaryModel):
    data: BlockerResolvedAuditData
    operation: Literal["blocker_resolved"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2)]


class WorkDeferredAuditPayload(_BoundaryModel):
    data: DeferredAuditData
    operation: Literal["deferred"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2)]


class WorkReceipt(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    operation: Literal[
        "priority_changed",
        "assignment_changed",
        "admitted",
        "deferred",
        "blocker_opened",
        "blocker_resolved",
        "reopened",
        "relation_added",
    ]
    ticket_id: UUID
    version: Annotated[int, Field(ge=2)]


class WorkRelationAddedAuditPayload(_BoundaryModel):
    data: RelationAddedAuditData
    operation: Literal["relation_added"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2)]


class WorkflowChangedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["workflow.changed"]
    occurred_at: datetime
    payload: WorkflowChangedAuditPayload
    record_position: Annotated[int, Field(ge=1)]
    sequence: Annotated[int, Field(ge=1)]
    stream_id: Annotated[str, Field(pattern="^workflow:[0-9a-f-]{36}$")]


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


class AssignmentList(_BoundaryModel):
    assignments: tuple[AssignmentInterval, ...]
    ticket_id: UUID


class BoardView(_BoundaryModel):
    cards: tuple[BoardCard, ...]
    health: ProjectionHealth
    projection_watermark: Annotated[int, Field(ge=0)]
    source_watermark: Annotated[int, Field(ge=0)]


class TicketCommandResult(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    ticket: TicketResource


class TicketCreatedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["ticket.created"]
    occurred_at: datetime
    payload: TicketCreatedPayload
    record_position: Annotated[int, Field(ge=1)]
    sequence: Annotated[int, Field(ge=1)]
    stream_id: Annotated[str, Field(pattern="^ticket:[0-9a-f-]{36}$")]


class TimelineEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_id: UUID
    kind: Literal["ticket.created", "ticket.custody_transferred"]
    occurred_at: datetime
    payload: TicketCreatedPayload | CustodyTransferredPayload
    sequence: Annotated[int, Field(ge=1)]


class WorkPriorityChangedAuditPayload(_BoundaryModel):
    data: PriorityChangedAuditData
    operation: Literal["priority_changed"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2)]


class WorkReopenedAuditPayload(_BoundaryModel):
    data: ReopenedAuditData
    operation: Literal["reopened"]
    ticket_id: UUID
    work_version: Annotated[int, Field(ge=2)]


class TimelineResponse(_BoundaryModel):
    durability_state: DurabilityState
    events: tuple[TimelineEvent, ...]
    ticket_id: UUID


type WorkChangedAuditPayload = WorkPriorityChangedAuditPayload | WorkAssignmentChangedAuditPayload | WorkAdmittedAuditPayload | WorkDeferredAuditPayload | WorkBlockerOpenedAuditPayload | WorkBlockerResolvedAuditPayload | WorkReopenedAuditPayload | WorkRelationAddedAuditPayload


class WorkChangedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["work.changed"]
    occurred_at: datetime
    payload: WorkChangedAuditPayload
    record_position: Annotated[int, Field(ge=1)]
    sequence: Annotated[int, Field(ge=1)]
    stream_id: Annotated[str, Field(pattern="^ticket:[0-9a-f-]{36}$")]


type AuditEvent = TicketCreatedAuditEvent | CustodyTransferredAuditEvent | WorkChangedAuditEvent | WorkflowChangedAuditEvent | ProofChangedAuditEvent


class AuditPage(_BoundaryModel):
    events: tuple[AuditEvent, ...]
    next_cursor: Annotated[int, Field(ge=1)] | None
    ticket_id: UUID
