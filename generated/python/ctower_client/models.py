"""DO NOT EDIT: generated file; regenerate from declared inputs.

Authored contract digest: sha256:17cf75a06dc1b6485702746d67fe72fdf16f73b35fe11f9fe7e5fb30a3c62611
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
    "BundleAction",
    "BundleActionKind",
    "BundleCheck",
    "CompanyBundleApplyRequest",
    "CompanyBundleAssignment",
    "CompanyBundleCommandResult",
    "CompanyBundleDocument",
    "CompanyBundleExportMetadata",
    "CompanyBundleExportResult",
    "CompanyBundlePlan",
    "CompanyBundleRequest",
    "CompanyBundleResource",
    "CompanyBundleValidationResult",
    "CompanyIdentity",
    "ComponentCompatibility",
    "ComponentKind",
    "ComponentProvenance",
    "ComponentReference",
    "ComponentScope",
    "ControlHealth",
    "CtowerProjectAliasPlanBindRequest",
    "CtowerProjectCutoverHealth",
    "CtowerProjectEpochRefusalRequest",
    "CtowerProjectExactAliasOperation",
    "CtowerProjectExportEqualityBindRequest",
    "CtowerProjectFenceObservationRequest",
    "CtowerProjectImportBatchRequest",
    "CtowerProjectImportBatchResult",
    "CtowerProjectImportCorrectionRequest",
    "CtowerProjectImportFinalizeRequest",
    "CtowerProjectImportOperation",
    "CtowerProjectImportRun",
    "CtowerProjectImportRunCreateRequest",
    "CtowerProjectMigrationReceipt",
    "CtowerProjectReconciliationResult",
    "CtowerProjectSourceLinkOperation",
    "CtowerProjectTicketRelationOperation",
    "CtowerProjectTicketSeedOperation",
    "CustodyTransferRequest",
    "CustodyTransferredAuditEvent",
    "CustodyTransferredPayload",
    "DeferIntent",
    "DeferredAuditData",
    "DurabilityState",
    "EvidenceRequest",
    "FreezeCriteriaRequest",
    "HealthContributor",
    "HealthContributorKey",
    "HealthDimension",
    "HealthStatus",
    "MigrationAliasCorrection",
    "MigrationConservation",
    "MigrationCorrectionReplacement",
    "MigrationCorrectionRevision",
    "MigrationDispositions",
    "MigrationFenceFileIdentity",
    "MigrationHealthDigests",
    "MigrationImportCounts",
    "MigrationImportOperationResult",
    "MigrationImporterBinding",
    "MigrationOperationIdentity",
    "MigrationPinnedDigests",
    "MigrationRefusal",
    "MigrationRelationCorrection",
    "MigrationSourceIdentity",
    "MigrationSourceLinkCorrection",
    "MutableAssignmentKind",
    "PoisonDispositionAction",
    "PoisonDispositionReceipt",
    "PoisonDispositionRequest",
    "Priority",
    "PriorityChangeRequest",
    "PriorityChangedAuditData",
    "Problem",
    "ProjectDeliveryCriteria",
    "ProjectDeliveryRow",
    "ProjectDeliveryView",
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
    "SecretBindingReference",
    "SourceReference",
    "SyntheticRunReceipt",
    "SyntheticRunRequest",
    "SyntheticRunResource",
    "SyntheticRunState",
    "TelemetryContext",
    "TicketCommandResult",
    "TicketCommentAddedAuditEvent",
    "TicketCommentAddedPayload",
    "TicketCommentRequest",
    "TicketCommentResult",
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
    "VersionedComponent",
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


class BundleActionKind(StrEnum):
    CREATE = "create"
    REUSE_EXACT = "reuse_exact"
    SUPERSEDE = "supersede"
    DEPRECATE = "deprecate"
    ASSIGNMENT_CHANGE = "assignment_change"
    POINTER_CHANGE = "pointer_change"
    NO_OP = "no_op"


class BundleCheck(_BoundaryModel):
    code: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,95}$")]
    status: Literal["passed", "warning"]


class CompanyIdentity(_BoundaryModel):
    display_name: Annotated[str, Field(min_length=1, max_length=128)]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]


class ComponentKind(StrEnum):
    WORKFLOW = "workflow"
    EXECUTION_POLICY = "execution_policy"
    GATE_POLICY = "gate_policy"
    EVIDENCE_POLICY = "evidence_policy"
    GOAL = "goal"
    PROJECT = "project"
    AGENT_PROFILE = "agent_profile"
    PERSONA = "persona"
    SKILL = "skill"
    TOOL = "tool"
    CAPABILITY = "capability"
    ENVIRONMENT = "environment"
    IMAGE = "image"
    HARNESS = "harness"
    SUPERVISOR = "supervisor"
    TARGET = "target"
    WORKSPACE = "workspace"
    TELEMETRY = "telemetry"
    PLACEMENT_POLICY = "placement_policy"
    EXTENSION = "extension"
    CADENCE_POLICY = "cadence_policy"
    NOTIFICATION = "notification"
    INTEGRATION = "integration"
    ADAPTER = "adapter"
    CHECKPOINT = "checkpoint"


class ComponentProvenance(_BoundaryModel):
    digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    kind: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,63}$")]
    source: Annotated[str, Field(min_length=1, max_length=512)]


class ComponentScope(_BoundaryModel):
    project: Annotated[str, Field(pattern="^[a-z][a-z0-9.-]{2,127}$")] | None
    tenant: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]


class CtowerProjectAliasPlanBindRequest(_BoundaryModel):
    run_id: UUID
    cutover_id: UUID
    export_equality_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    alias_map_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reviewer_public_key_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    attention_required: Literal[0]


class CtowerProjectEpochRefusalRequest(_BoundaryModel):
    cutover_id: UUID
    run_id: UUID
    reconciliation_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    fence_registry_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class CtowerProjectExportEqualityBindRequest(_BoundaryModel):
    run_id: UUID
    cutover_id: UUID
    selection_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    inventory_a_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    inventory_b_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    export_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    equality_report_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reviewer_public_key_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    result: Literal["equal"]


class CtowerProjectImportFinalizeRequest(_BoundaryModel):
    run_id: UUID
    cutover_id: UUID
    expected_run_semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class CtowerProjectImportRunCreateRequest(_BoundaryModel):
    cutover_id: UUID
    tenant_key: Literal["ctower"]
    project_key: Literal["ctower"]
    source_selection_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    build_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    client_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    schema_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    operation_registry_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reviewer_public_key_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    importer_credential_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    importer_expires_at: datetime


class CtowerProjectMigrationReceipt(_BoundaryModel):
    object_id: UUID
    revision: Annotated[int, Field(ge=1)]
    command_id: UUID
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    record_position: Annotated[int, Field(ge=1)]
    semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    durability_state: Literal["durability_pending"]
    accepted_position: None


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


class HealthContributorKey(StrEnum):
    DURABILITY = "durability"
    SCHEDULER = "scheduler"
    OUTBOX = "outbox"
    PROJECTION = "projection"
    BACKUP = "backup"
    ANCHOR = "anchor"
    OBJECT = "object"
    SYNTHETIC = "synthetic"


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STATE_UNKNOWN = "STATE_UNKNOWN"


class MigrationAliasCorrection(_BoundaryModel):
    kind: Literal["alias"]
    target_ticket_id: UUID
    disposition: Literal["alias_linked_existing", "exact_duplicate", "provenance_only"]


class MigrationConservation(_BoundaryModel):
    selected_logical_items: Annotated[int, Field(ge=1)]
    selected_request_logical: Literal[86]
    selected_request_physical_snapshots: Literal[243]
    stable_aliases: Literal[27]
    checkpoint_definitions: Literal[14]
    unresolved_aliases: Literal[0]
    alias_forks_or_cycles: Literal[0]
    missing_relation_endpoints: Literal[0]
    forbidden_relation_cycles: Literal[0]
    unresolved_active_claims: Literal[0]
    unexpected_sources: Literal[0]
    forbidden_data_items: Literal[0]
    pass_two_new_domain_facts: Literal[0]
    pass_two_new_events: Literal[0]
    pass_two_new_outbox_rows: Literal[0]
    pass_two_record_position_delta: Literal[0]
    pass_two_projection_semantic_delta: Literal[0]


class MigrationCorrectionRevision(_BoundaryModel):
    object_id: UUID
    revision: Annotated[int, Field(ge=1)]


class MigrationDispositions(_BoundaryModel):
    created_ticket: Annotated[int, Field(ge=0)]
    alias_linked_existing: Annotated[int, Field(ge=0)]
    project_checkpoint_definition: Annotated[int, Field(ge=0)]
    decision_link: Annotated[int, Field(ge=0)]
    external_effect_link: Annotated[int, Field(ge=0)]
    artifact_linked_not_proof: Annotated[int, Field(ge=0)]
    provenance_only: Annotated[int, Field(ge=0)]
    exact_duplicate: Annotated[int, Field(ge=0)]
    excluded_out_of_scope: Annotated[int, Field(ge=0)]
    attention_required: Literal[0]


class MigrationFenceFileIdentity(_BoundaryModel):
    device: Annotated[int, Field(ge=0)]
    inode: Annotated[int, Field(ge=1)]
    scoped_rows_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class MigrationHealthDigests(_BoundaryModel):
    source_selection: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    export_equality: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    alias_map: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    reconciliation: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    fence_registry: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    fence_observation: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None


class MigrationImportCounts(_BoundaryModel):
    planned_operations: Annotated[int, Field(ge=0)]
    applied_operations: Annotated[int, Field(ge=0)]
    replayed_operations: Annotated[int, Field(ge=0)]
    refused_operations: Annotated[int, Field(ge=0)]


class MigrationImportOperationResult(_BoundaryModel):
    command_id: UUID
    operation_kind: Literal["ticket_seed", "exact_alias", "ticket_relation", "source_link"]
    replayed: bool
    target_id: Annotated[str, Field(min_length=1, max_length=256)]
    event_ids: tuple[UUID, ...]
    record_position: Annotated[int, Field(ge=1)]
    occurred_at: datetime


class MigrationImporterBinding(_BoundaryModel):
    principal_kind: Literal["migration_importer"]
    credential_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    expires_at: datetime
    revoked: bool


class MigrationOperationIdentity(_BoundaryModel):
    namespace: Annotated[str, Field(min_length=1, max_length=128)]
    immutable_source_id: Annotated[str, Field(min_length=1, max_length=512)]
    source_version_or_digest: Annotated[str, Field(min_length=1, max_length=256)]
    operation_kind: Literal["ticket_seed", "exact_alias", "ticket_relation", "source_link"]
    planned_target_ref: Annotated[str, Field(min_length=1, max_length=256)]
    command_id: UUID


class MigrationPinnedDigests(_BoundaryModel):
    source_selection: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    export_equality: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    alias_map: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    build: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    client: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    schema_id: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] = Field(
        alias="schema", serialization_alias="schema"
    )
    operation_registry: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reviewer_public_key: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class MigrationRefusal(_BoundaryModel):
    code: Annotated[str, Field(pattern="^[A-Z][A-Z0-9_]{2,95}$")]
    operation_identity: Annotated[str, Field(min_length=1, max_length=512)]


class MigrationRelationCorrection(_BoundaryModel):
    kind: Literal["relation"]
    superseded_relation_active: Literal[False]
    replacement_relation_id: UUID | None


class MigrationSourceIdentity(_BoundaryModel):
    namespace: Annotated[str, Field(min_length=1, max_length=128)]
    immutable_source_id: Annotated[str, Field(min_length=1, max_length=512)]
    source_version: Annotated[str, Field(min_length=1, max_length=256)]
    source_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class MigrationSourceLinkCorrection(_BoundaryModel):
    kind: Literal["source_link"]
    target_kind: Literal[
        "ticket",
        "ticket_relation",
        "checkpoint",
        "decision",
        "artifact",
        "external_effect",
    ]
    target_id: Annotated[str, Field(min_length=1, max_length=256)]
    disposition: Literal[
        "decision_link",
        "external_effect_link",
        "artifact_linked_not_proof",
        "provenance_only",
        "excluded_out_of_scope",
    ]


class MutableAssignmentKind(StrEnum):
    CURRENT_ASSIGNEE = "current_assignee"
    STAGE_OWNER = "stage_owner"
    REVIEWER_ASSIGNMENT = "reviewer_assignment"


class PoisonDispositionAction(StrEnum):
    RETRY = "retry"
    TOMBSTONE = "tombstone"


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
        "bundle-base-conflict",
        "bundle-compatibility-refused",
        "bundle-digest-mismatch",
        "bundle-grant-refused",
        "bundle-independence-refused",
        "bundle-no-effect-refused",
        "bundle-not-active",
        "bundle-plan-mismatch",
        "bundle-recovery-unavailable",
        "bundle-reference-invalid",
        "bundle-schema-invalid",
        "bundle-security-refused",
        "durability_pending",
        "i1-7c-required",
        "idempotency-conflict",
        "migration-alias-conflict",
        "migration-capability-denied",
        "migration-correction-conflict",
        "migration-digest-mismatch",
        "migration-export-nondeterminism",
        "migration-fence-detected",
        "migration-import-finalization-refused",
        "migration-operation-drift",
        "migration-relation-invalid",
        "migration-run-conflict",
        "migration-signature-invalid",
        "migration-source-selection-drift",
        "migration-source-tainted",
        "poison-not-found",
        "project-delivery-unavailable",
        "proof-candidate-author-mismatch",
        "proof-candidate-digest-invalid",
        "proof-candidate-digest-not-current",
        "proof-candidate-unchanged",
        "proof-criteria-already-frozen",
        "proof-criteria-invalid",
        "proof-criteria-policy-mismatch",
        "proof-criterion-unknown",
        "proof-current-evidence-missing",
        "proof-evidence-digest-mismatch",
        "proof-evidence-id-conflict",
        "proof-protected-authority-required",
        "proof-policy-mismatch",
        "proof-policy-pin-mismatch",
        "proof-self-review-refused",
        "proof-verdict-id-conflict",
        "tenant-scope-denied",
        "ticket-comment-ineligible",
        "ticket-comment-invalid",
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
        "work-ticket-terminal",
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


class ProjectDeliveryCriteria(_BoundaryModel):
    proven: Annotated[int, Field(ge=0)]
    declared: Annotated[int, Field(ge=1)]


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


class SecretBindingReference(_BoundaryModel):
    name: Annotated[str, Field(pattern="^[A-Z][A-Z0-9_]{2,127}$")]
    reference_class: Literal["os-credential", "vault-path", "runtime-binding"]


class SourceReference(_BoundaryModel):
    kind: Annotated[str, Field(min_length=1, max_length=64)]
    ref: Annotated[str, Field(min_length=1, max_length=256)]


class SyntheticRunRequest(_BoundaryModel):
    workflow_ref: Literal["ctower.trust-spine-four-stage@1"]


class SyntheticRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


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


class TicketCommentAddedPayload(_BoundaryModel):
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    comment_id: UUID
    ticket_id: UUID


class TicketCommentRequest(_BoundaryModel):
    body: Annotated[str, Field(min_length=1, max_length=4000)]


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


class CompanyBundleCommandResult(_BoundaryModel):
    active_version: Annotated[int, Field(ge=1)]
    bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    plan_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class CompanyBundleExportMetadata(_BoundaryModel):
    activated_at: datetime
    actor_principal_id: UUID
    checks: tuple[BundleCheck, ...]
    command_id: UUID


class CompanyBundleValidationResult(_BoundaryModel):
    bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    checks: tuple[BundleCheck, ...]
    valid: bool
    warnings: tuple[Annotated[str, Field(max_length=500)], ...]


class ComponentReference(_BoundaryModel):
    content_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9.-]{2,127}$")]
    kind: ComponentKind
    revision: Annotated[int, Field(ge=1)]


class CtowerProjectCutoverHealth(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-cutover-health/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    cutover_id: UUID | None
    authority_mode: Literal["legacy_writable", "development_single_writer", "disaster_safe"]
    phase: Literal[
        "not_started",
        "source_selection_frozen",
        "export_equal",
        "alias_plan_bound",
        "import_in_progress",
        "reconciled",
        "prepared",
        "development_epoch_committed",
        "disaster_safe_active",
    ]
    writes_enabled: bool
    durability_claim: Literal["CP3_D_NOT_PROVEN", "CP3_D_PROVEN"]
    recovery_claim: Literal["EXTERNAL_FAILURE_DOMAIN_UNPROVEN", "EXTERNAL_FAILURE_DOMAIN_PROVEN"]
    data_class: Literal["RECONSTRUCTIBLE_ONLY", "DISASTER_SAFE_CTOWER_ENGINEERING"]
    legacy_writer_fence: Literal["not_armed", "enforced", "unknown"]
    split_brain: Literal["clear", "detected", "unknown"]
    projection_completeness: Literal["current", "stale", "STATE_UNKNOWN"]
    source_watermark: Annotated[int, Field(ge=0)]
    projection_watermark: Annotated[int, Field(ge=0)]
    import_run_id: UUID | None
    migration_digests: MigrationHealthDigests
    banner: Annotated[str, Field(min_length=1)]


class CtowerProjectExactAliasOperation(_BoundaryModel):
    operation: Literal["exact_alias"]
    identity: MigrationOperationIdentity
    project_key: Literal["ctower"]
    source: MigrationSourceIdentity
    target_ticket_id: UUID


class CtowerProjectFenceObservationRequest(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-fence-observation/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    observation_id: UUID
    registry_id: UUID
    registry_revision: Annotated[int, Field(ge=1)]
    registry_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    sequence: Annotated[int, Field(ge=1)]
    previous_observation_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    observed_at: datetime
    from_offset: Annotated[int, Field(ge=0)]
    to_offset: Annotated[int, Field(ge=0)]
    file_identity: MigrationFenceFileIdentity
    status: Literal["clear", "detected", "unknown"]
    reason_code: Literal[
        "no_scoped_append",
        "scoped_row_appended",
        "truncated_row",
        "inode_replaced",
        "file_truncated",
        "unreadable_gap",
        "classifier_unknown",
        "monitor_interval_missing",
        "registry_mismatch",
    ]
    observation_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    disables_writes: bool
    may_enable_writes: Literal[False]


class CtowerProjectImportBatchResult(_BoundaryModel):
    run_id: UUID
    batch_index: Annotated[int, Field(ge=0)]
    batch_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    results: Annotated[tuple[MigrationImportOperationResult, ...], Field(min_length=1, max_length=64)]
    record_watermark: Annotated[int, Field(ge=1)]
    projection_watermark: Annotated[int, Field(ge=0)]
    durability_state: Literal["durability_pending"]
    accepted_position: None


class CtowerProjectImportRun(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-import-run/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    run_id: UUID
    cutover_id: UUID
    tenant_key: Literal["ctower"]
    project_key: Literal["ctower"]
    state: Literal[
        "created",
        "export_equality_bound",
        "alias_plan_bound",
        "importing",
        "pass_one_complete",
        "pass_two_noop",
        "reconciled",
    ]
    pinned_digests: MigrationPinnedDigests
    importer_binding: MigrationImporterBinding
    counts: MigrationImportCounts
    record_watermark: Annotated[int, Field(ge=0)]
    projection_watermark: Annotated[int, Field(ge=0)]
    refusals: tuple[MigrationRefusal, ...]
    semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    durability_state: Literal["durability_pending"]
    accepted_position: None


class CtowerProjectReconciliationResult(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-reconciliation/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    reconciliation_id: UUID
    run_id: UUID
    cutover_id: UUID
    project_key: Literal["ctower"]
    pinned_digests: MigrationPinnedDigests
    dispositions: MigrationDispositions
    conservation: MigrationConservation
    source_native_watermark: Annotated[int, Field(ge=0)]
    export_native_watermark: Annotated[int, Field(ge=0)]
    record_watermark: Annotated[int, Field(ge=0)]
    projection_watermark: Annotated[int, Field(ge=0)]
    target_semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    report_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    durability_state: Literal["durability_pending"]
    accepted_position: None


class CtowerProjectSourceLinkOperation(_BoundaryModel):
    operation: Literal["source_link"]
    identity: MigrationOperationIdentity
    project_key: Literal["ctower"]
    source: MigrationSourceIdentity
    link_class: Literal["decision", "external_effect", "artifact_not_proof", "provenance"]
    target_kind: Literal[
        "ticket",
        "ticket_relation",
        "checkpoint",
        "decision",
        "artifact",
        "external_effect",
    ]
    target_id: Annotated[str, Field(min_length=1, max_length=256)]
    reason_code: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{2,95}$")]
    linked_not_proof: Literal[True]


class CtowerProjectTicketRelationOperation(_BoundaryModel):
    operation: Literal["ticket_relation"]
    identity: MigrationOperationIdentity
    project_key: Literal["ctower"]
    relation_id: UUID
    relation_kind: Literal["parent_of", "depends_on", "blocks", "duplicates", "relates_to", "caused_by"]
    source_ticket_id: UUID
    target_ticket_id: UUID
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class CtowerProjectTicketSeedOperation(_BoundaryModel):
    operation: Literal["ticket_seed"]
    identity: MigrationOperationIdentity
    project_key: Literal["ctower"]
    priority: Literal["P2"]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    source: MigrationSourceIdentity
    initial_commander_custodian_id: UUID


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


class HealthContributor(_BoundaryModel):
    key: HealthContributorKey
    status: HealthStatus
    watermark: Annotated[int, Field(ge=0)] | None
    threshold_seconds: Annotated[int, Field(ge=0)]
    observed_at: datetime
    owner: Annotated[str, Field(min_length=1, max_length=128)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]


type MigrationCorrectionReplacement = MigrationAliasCorrection | MigrationSourceLinkCorrection | MigrationRelationCorrection


class PoisonDispositionReceipt(_BoundaryModel):
    command_id: UUID
    outbox_id: UUID
    action: PoisonDispositionAction
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    recorded_at: datetime


class PoisonDispositionRequest(_BoundaryModel):
    consumer_key: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    topic: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*$")]
    action: PoisonDispositionAction
    reason: Annotated[str, Field(min_length=1, max_length=500)]


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


class ProjectDeliveryRow(_BoundaryModel):
    checkpoint_key: Annotated[str, Field(pattern="^I[12]\\.[0-9]+$")]
    checkpoint_label: Annotated[str, Field(min_length=1)]
    headline_state: Literal[
        "planned",
        "in_progress",
        "ready_to_land",
        "merged",
        "verified",
        "released",
        "blocked",
        "done",
    ]
    underlying_maturity: Literal["planned", "in_progress", "ready_to_land", "merged", "verified", "released"]
    outcome: Annotated[str, Field(min_length=1)]
    accountable_owner: Annotated[str, Field(min_length=1)]
    criteria: ProjectDeliveryCriteria
    source_watermark: Annotated[int, Field(ge=0)]
    projection_watermark: Annotated[int, Field(ge=0)]
    freshness: Literal["fresh", "stale", "STATE_UNKNOWN"]
    confidence: Literal["development_degraded", "disaster_safe", "STATE_UNKNOWN"]
    health: Literal["CP3_D_NOT_PROVEN", "CURRENT", "STATE_UNKNOWN"]
    durability: Literal["CP3_D_NOT_PROVEN", "CP3_D_PROVEN", "STATE_UNKNOWN"]
    recovery: Literal[
        "EXTERNAL_FAILURE_DOMAIN_UNPROVEN",
        "EXTERNAL_FAILURE_DOMAIN_PROVEN",
        "STATE_UNKNOWN",
    ]
    data_class: Literal["RECONSTRUCTIBLE_ONLY", "DISASTER_SAFE_CTOWER_ENGINEERING", "STATE_UNKNOWN"]
    semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    reconciled_at: datetime
    freshness_due_at: datetime
    rebuild_generation: Annotated[int, Field(ge=0)]
    source_ids: tuple[Annotated[str, Field(min_length=1)], ...]
    derivation_reasons: Annotated[tuple[Annotated[str, Field(min_length=1)], ...], Field(min_length=1)]


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


class SyntheticRunReceipt(_BoundaryModel):
    command_id: UUID
    durability_state: DurabilityState
    event_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    job_id: UUID
    run_id: UUID
    workflow_ref: Literal["ctower.trust-spine-four-stage@1"]


class SyntheticRunResource(_BoundaryModel):
    attempt_count: Annotated[int, Field(ge=0, le=8)]
    completed_at: datetime | None
    created_at: datetime
    detail_code: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{2,95}$")] | None
    job_id: UUID
    lifecycle_facts: Annotated[tuple[Literal["resolved", "closed"], ...], Field(max_length=2)]
    run_id: UUID
    state: SyntheticRunState
    ticket_id: UUID | None
    workflow_ref: Literal["ctower.trust-spine-four-stage@1"]


class TicketCommentAddedAuditEvent(_BoundaryModel):
    actor_principal_id: UUID
    command_id: UUID
    event_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    event_id: UUID
    kind: Literal["ticket.comment_added"]
    occurred_at: datetime
    payload: TicketCommentAddedPayload
    record_position: Annotated[int, Field(ge=1)]
    sequence: Annotated[int, Field(ge=1)]
    stream_id: Annotated[str, Field(pattern="^ticket:[0-9a-f-]{36}$")]


class TicketCommentResult(_BoundaryModel):
    command_id: UUID
    comment_id: UUID
    durability_state: DurabilityState
    event_id: UUID
    ticket_id: UUID


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


class BundleAction(_BoundaryModel):
    component: ComponentReference
    kind: BundleActionKind


class CompanyBundleAssignment(_BoundaryModel):
    component: ComponentReference
    slot: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]{1,63}$")]
    subject: Annotated[str, Field(pattern="^[a-z][a-z0-9._-]*:[a-z][a-z0-9._-]*$")]


class ComponentCompatibility(_BoundaryModel):
    ctower: Annotated[str, Field(min_length=1, max_length=80)]
    requires: Annotated[tuple[ComponentReference, ...], Field(max_length=128)]


class CtowerProjectImportCorrectionRequest(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-import-correction/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    correction_id: UUID
    run_id: UUID
    cutover_id: UUID
    tenant_key: Literal["ctower"]
    project_key: Literal["ctower"]
    correction_kind: Literal["alias", "source_link", "relation"]
    superseded_revision: MigrationCorrectionRevision
    expected_current_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    replacement: MigrationCorrectionReplacement
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    reviewer_id: UUID


type CtowerProjectImportOperation = CtowerProjectTicketSeedOperation | CtowerProjectExactAliasOperation | CtowerProjectTicketRelationOperation | CtowerProjectSourceLinkOperation


class HealthDimension(_BoundaryModel):
    status: HealthStatus
    contributors: Annotated[tuple[HealthContributor, ...], Field(min_length=1)]


class ProjectDeliveryView(_BoundaryModel):
    schema_id: Literal["ctower.project-delivery/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    company_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    project_key: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{2,63}$")]
    source_record_position: Annotated[int, Field(ge=0)]
    projection_record_position: Annotated[int, Field(ge=0)]
    reconciled_at: datetime
    freshness_due_at: datetime
    projection_semantic_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    rebuild_generation: Annotated[int, Field(ge=0)]
    rows: tuple[ProjectDeliveryRow, ...]


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
    kind: Literal["ticket.created", "ticket.custody_transferred", "ticket.comment_added"]
    occurred_at: datetime
    payload: TicketCreatedPayload | CustodyTransferredPayload | TicketCommentAddedPayload
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


class CompanyBundlePlan(_BoundaryModel):
    actions: tuple[BundleAction, ...]
    base_bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")] | None
    base_version: Annotated[int, Field(ge=0)]
    checks: tuple[BundleCheck, ...]
    plan_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    proposed_bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    warnings: tuple[Annotated[str, Field(max_length=500)], ...]


class ControlHealth(_BoundaryModel):
    schema_id: Literal["ctower.health/v1"]
    status: HealthStatus
    observed_at: datetime
    availability: HealthDimension
    completeness: HealthDimension
    integrity: HealthDimension


class CtowerProjectImportBatchRequest(_BoundaryModel):
    schema_id: Literal["ctower.ctower-project-import-batch/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    run_id: UUID
    cutover_id: UUID
    batch_index: Annotated[int, Field(ge=0)]
    batch_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    operations: Annotated[tuple[CtowerProjectImportOperation, ...], Field(min_length=1, max_length=64)]


class TimelineResponse(_BoundaryModel):
    durability_state: DurabilityState
    events: tuple[TimelineEvent, ...]
    ticket_id: UUID


class VersionedComponent(_BoundaryModel):
    compatibility: ComponentCompatibility
    content_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    key: Annotated[str, Field(pattern="^[a-z][a-z0-9.-]{2,127}$")]
    kind: ComponentKind
    lifecycle: Literal["draft", "published", "deprecated", "revoked"]
    payload_ref: Annotated[str, Field(pattern="^object:sha256:[0-9a-f]{64}$")]
    provenance: Annotated[tuple[ComponentProvenance, ...], Field(min_length=1, max_length=64)]
    revision: Annotated[int, Field(ge=1)]
    schema_id: Literal["ctower.versioned-component/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    schema_ref: Annotated[str, Field(pattern="^ctower\\.[a-z][a-z0-9.-]*/v[1-9][0-9]*$")]
    scope: ComponentScope
    supersedes: ComponentReference | None = None


type WorkChangedAuditPayload = WorkPriorityChangedAuditPayload | WorkAssignmentChangedAuditPayload | WorkAdmittedAuditPayload | WorkDeferredAuditPayload | WorkBlockerOpenedAuditPayload | WorkBlockerResolvedAuditPayload | WorkReopenedAuditPayload | WorkRelationAddedAuditPayload


class CompanyBundleResource(_BoundaryModel):
    component: VersionedComponent
    payload: dict[str, object]


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


type AuditEvent = TicketCreatedAuditEvent | CustodyTransferredAuditEvent | TicketCommentAddedAuditEvent | WorkChangedAuditEvent | WorkflowChangedAuditEvent | ProofChangedAuditEvent


class CompanyBundleDocument(_BoundaryModel):
    assignments: Annotated[tuple[CompanyBundleAssignment, ...], Field(max_length=512)]
    company: CompanyIdentity
    resources: Annotated[tuple[CompanyBundleResource, ...], Field(min_length=1, max_length=512)]
    schema_id: Literal["ctower.company-bundle/v1"] = Field(
        alias="schema", serialization_alias="schema"
    )
    secret_binding_refs: Annotated[tuple[SecretBindingReference, ...], Field(max_length=128)]


class AuditPage(_BoundaryModel):
    events: tuple[AuditEvent, ...]
    next_cursor: Annotated[int, Field(ge=1)] | None
    ticket_id: UUID


class CompanyBundleApplyRequest(_BoundaryModel):
    bundle: CompanyBundleDocument
    expected_active_version: Annotated[int, Field(ge=0)]
    plan_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class CompanyBundleExportResult(_BoundaryModel):
    active_version: Annotated[int, Field(ge=1)]
    bundle: CompanyBundleDocument
    bundle_digest: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    metadata: CompanyBundleExportMetadata


class CompanyBundleRequest(_BoundaryModel):
    bundle: CompanyBundleDocument
