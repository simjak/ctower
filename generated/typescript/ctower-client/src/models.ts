// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:3294b213de71af8ec8857df7f43c9b5927f8d71b952b47a2c9b59f9b385f3cbe

export type ActivityClass = "work" | "verification";

export type AdmitIntent = Readonly<{
  readonly "expected_version": number;
  readonly "kind": "admit";
  readonly "reason": string;
}>;

export type AdmittedAuditData = Readonly<{
  readonly "episode_number": number;
  readonly "reason": string;
}>;

export type AssignmentChangeRequest = Readonly<{
  readonly "assignment_kind": MutableAssignmentKind;
  readonly "expected_version": number;
  readonly "reason": string;
  readonly "scope_ref"?: string | null;
  readonly "to_principal_id": string;
}>;

export type AssignmentChangedAuditData = Readonly<{
  readonly "assignment_kind": "current_assignee" | "stage_owner" | "reviewer_assignment";
  readonly "from_principal_id": string | null;
  readonly "reason": string;
  readonly "scope_ref": string | null;
  readonly "to_principal_id": string;
}>;

export type AssignmentInterval = Readonly<{
  readonly "assigned_at": string;
  readonly "assignment_kind": AssignmentKind;
  readonly "changed_by": string;
  readonly "episode_number": number;
  readonly "principal_id": string;
  readonly "reason": string;
  readonly "released_at": string | null;
  readonly "scope_ref": string | null;
  readonly "sequence": number;
}>;

export type AssignmentKind = "ticket_custodian" | "current_assignee" | "stage_owner" | "reviewer_assignment" | "runner_lease_owner";

export type AssignmentList = Readonly<{
  readonly "assignments": ReadonlyArray<AssignmentInterval>;
  readonly "ticket_id": string;
}>;

export type AuditEvent = TicketCreatedAuditEvent | CustodyTransferredAuditEvent | TicketCommentAddedAuditEvent | WorkChangedAuditEvent | WorkflowChangedAuditEvent | ProofChangedAuditEvent;

export type AuditPage = Readonly<{
  readonly "events": ReadonlyArray<AuditEvent>;
  readonly "next_cursor": number | null;
  readonly "ticket_id": string;
}>;

export type BlockIntent = Readonly<{
  readonly "affected_stage": string | null;
  readonly "blocker_id": string;
  readonly "blocker_kind": "dependency" | "operator_action" | "policy" | "resource" | "technical";
  readonly "board_impact": boolean;
  readonly "dependency_ref": string | null;
  readonly "expected_version": number;
  readonly "kind": "block";
  readonly "next_check_at": string | null;
  readonly "owner_principal_id": string;
  readonly "reason": string;
  readonly "reason_class": string;
  readonly "resolution_condition": string;
  readonly "source_ref": string;
}>;

export type BlockerOpenedAuditData = Readonly<{
  readonly "blocker_id": string;
  readonly "board_impact": boolean;
  readonly "reason": string;
}>;

export type BlockerResolvedAuditData = Readonly<{
  readonly "blocker_id": string;
  readonly "reason": string;
  readonly "resolution_evidence_ref": string;
}>;

export type BoardCard = Readonly<{
  readonly "activity_class": "work" | "verification" | null;
  readonly "assignee_id": string | null;
  readonly "blocker_opened_at": string | null;
  readonly "blocker_reason": string | null;
  readonly "custodian_id": string;
  readonly "delivery_facts": ReadonlyArray<string>;
  readonly "lane": BoardLane;
  readonly "priority": Priority;
  readonly "project_key": string;
  readonly "risk": string | null;
  readonly "stage_key": string | null;
  readonly "stage_label": string | null;
  readonly "ticket_id": string;
  readonly "title": string;
  readonly "underlying_lane": "backlog" | "ready" | "in_progress" | "in_review" | "complete" | null;
  readonly "version": number;
}>;

export type BoardLane = "backlog" | "ready" | "in_progress" | "in_review" | "blocked" | "complete";

export type BoardView = Readonly<{
  readonly "cards": ReadonlyArray<BoardCard>;
  readonly "health": ProjectionHealth;
  readonly "projection_watermark": number;
  readonly "source_watermark": number;
}>;

export type BootstrapReceipt = Readonly<{
  readonly "command_id": string;
  readonly "commander_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "operator_id": string;
  readonly "receipt_digest": string;
  readonly "tenant_id": string;
}>;

export type BootstrapRequest = Readonly<{
  readonly "commander_name": string;
  readonly "commander_vault_ref": string;
  readonly "operator_credential_ref": string;
  readonly "operator_name": string;
  readonly "operator_vault_ref": string;
  readonly "tenant_name": string;
  readonly "tenant_slug": string;
}>;

export type BundleAction = Readonly<{
  readonly "component": ComponentReference;
  readonly "kind": BundleActionKind;
}>;

export type BundleActionKind = "create" | "reuse_exact" | "supersede" | "deprecate" | "assignment_change" | "pointer_change" | "no_op";

export type BundleCheck = Readonly<{
  readonly "code": string;
  readonly "status": "passed" | "warning";
}>;

export type CompanyBundleApplyRequest = Readonly<{
  readonly "bundle": CompanyBundleDocument;
  readonly "expected_active_version": number;
  readonly "plan_digest": string;
}>;

export type CompanyBundleAssignment = Readonly<{
  readonly "component": ComponentReference;
  readonly "slot": string;
  readonly "subject": string;
}>;

export type CompanyBundleCommandResult = Readonly<{
  readonly "active_version": number;
  readonly "bundle_digest": string;
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "plan_digest": string;
}>;

export type CompanyBundleDocument = Readonly<{
  readonly "assignments": ReadonlyArray<CompanyBundleAssignment>;
  readonly "company": CompanyIdentity;
  readonly "resources": ReadonlyArray<CompanyBundleResource>;
  readonly "schema": "ctower.company-bundle/v1";
  readonly "secret_binding_refs": ReadonlyArray<SecretBindingReference>;
}>;

export type CompanyBundleExportMetadata = Readonly<{
  readonly "activated_at": string;
  readonly "actor_principal_id": string;
  readonly "checks": ReadonlyArray<BundleCheck>;
  readonly "command_id": string;
}>;

export type CompanyBundleExportResult = Readonly<{
  readonly "active_version": number;
  readonly "bundle": CompanyBundleDocument;
  readonly "bundle_digest": string;
  readonly "metadata": CompanyBundleExportMetadata;
}>;

export type CompanyBundlePlan = Readonly<{
  readonly "actions": ReadonlyArray<BundleAction>;
  readonly "base_bundle_digest": string | null;
  readonly "base_version": number;
  readonly "checks": ReadonlyArray<BundleCheck>;
  readonly "plan_digest": string;
  readonly "proposed_bundle_digest": string;
  readonly "warnings": ReadonlyArray<string>;
}>;

export type CompanyBundleRequest = Readonly<{
  readonly "bundle": CompanyBundleDocument;
}>;

export type CompanyBundleResource = Readonly<{
  readonly "component": VersionedComponent;
  readonly "payload": Readonly<Record<string, unknown>>;
}>;

export type CompanyBundleValidationResult = Readonly<{
  readonly "bundle_digest": string;
  readonly "checks": ReadonlyArray<BundleCheck>;
  readonly "valid": boolean;
  readonly "warnings": ReadonlyArray<string>;
}>;

export type CompanyIdentity = Readonly<{
  readonly "display_name": string;
  readonly "key": string;
}>;

export type ComponentCompatibility = Readonly<{
  readonly "ctower": string;
  readonly "requires": ReadonlyArray<ComponentReference>;
}>;

export type ComponentKind = "workflow" | "execution_policy" | "gate_policy" | "evidence_policy" | "goal" | "project" | "agent_profile" | "persona" | "skill" | "tool" | "capability" | "environment" | "image" | "harness" | "supervisor" | "target" | "workspace" | "telemetry" | "placement_policy" | "extension" | "cadence_policy" | "notification" | "integration" | "adapter" | "checkpoint";

export type ComponentProvenance = Readonly<{
  readonly "digest": string;
  readonly "kind": string;
  readonly "source": string;
}>;

export type ComponentReference = Readonly<{
  readonly "content_digest": string;
  readonly "key": string;
  readonly "kind": ComponentKind;
  readonly "revision": number;
}>;

export type ComponentScope = Readonly<{
  readonly "project": string | null;
  readonly "tenant": string;
}>;

export type ControlHealth = Readonly<{
  readonly "availability": HealthDimension;
  readonly "completeness": HealthDimension;
  readonly "integrity": HealthDimension;
  readonly "observed_at": string;
  readonly "schema_id": "ctower.health/v1";
  readonly "status": HealthStatus;
}>;

export type CtowerProjectAliasPlanBindRequest = Readonly<{
  readonly "alias_map_artifact": string;
  readonly "alias_map_digest": string;
  readonly "attention_required": 0;
  readonly "cutover_id": string;
  readonly "export_equality_digest": string;
  readonly "fence_observer_credential_digest": string;
  readonly "fence_observer_expires_at": string;
  readonly "fence_registry_artifact": string;
  readonly "import_plan_artifact": string;
  readonly "reviewer_key_ref": string;
  readonly "reviewer_key_version": number;
  readonly "reviewer_public_key_digest": string;
  readonly "run_id": string;
}>;

export type CtowerProjectCutoverHealth = Readonly<{
  readonly "authority_mode": "legacy_writable" | "development_single_writer" | "disaster_safe";
  readonly "banner": string;
  readonly "cutover_id": string | null;
  readonly "data_class": "RECONSTRUCTIBLE_ONLY" | "DISASTER_SAFE_CTOWER_ENGINEERING";
  readonly "durability_claim": "CP3_D_NOT_PROVEN" | "CP3_D_PROVEN";
  readonly "import_run_id": string | null;
  readonly "legacy_writer_fence": "not_armed" | "enforced" | "unknown";
  readonly "migration_digests": MigrationHealthDigests;
  readonly "phase": "not_started" | "source_selection_frozen" | "export_equal" | "alias_plan_bound" | "import_in_progress" | "reconciled" | "prepared" | "development_epoch_committed" | "disaster_safe_active";
  readonly "projection_completeness": "current" | "stale" | "STATE_UNKNOWN";
  readonly "projection_watermark": number;
  readonly "recovery_claim": "EXTERNAL_FAILURE_DOMAIN_UNPROVEN" | "EXTERNAL_FAILURE_DOMAIN_PROVEN";
  readonly "schema": "ctower.ctower-project-cutover-health/v1";
  readonly "source_watermark": number;
  readonly "split_brain": "clear" | "detected" | "unknown";
  readonly "writes_enabled": boolean;
}>;

export type CtowerProjectEpochRefusalRequest = Readonly<{
  readonly "cutover_id": string;
  readonly "fence_registry_digest": string;
  readonly "reconciliation_digest": string;
  readonly "run_id": string;
}>;

export type CtowerProjectExactAliasOperation = Readonly<{
  readonly "identity": MigrationOperationIdentity;
  readonly "operation": "exact_alias";
  readonly "project_key": "ctower";
  readonly "source": MigrationSourceIdentity;
  readonly "target_ticket_id": string;
}>;

export type CtowerProjectExportEqualityBindRequest = Readonly<{
  readonly "cutover_id": string;
  readonly "equality_report_digest": string;
  readonly "export_a_artifact": string;
  readonly "export_b_artifact": string;
  readonly "export_digest": string;
  readonly "export_equality_artifact": string;
  readonly "inventory_a_digest": string;
  readonly "inventory_b_digest": string;
  readonly "result": "equal";
  readonly "reviewer_key_ref": string;
  readonly "reviewer_key_version": number;
  readonly "reviewer_public_key_digest": string;
  readonly "run_id": string;
  readonly "selection_digest": string;
}>;

export type CtowerProjectFenceObservationRequest = Readonly<{
  readonly "cutover_id": string;
  readonly "disables_writes": boolean;
  readonly "file_identity": MigrationFenceFileIdentity;
  readonly "from_offset": number;
  readonly "may_enable_writes": false;
  readonly "observation_digest": string;
  readonly "observation_id": string;
  readonly "observed_at": string;
  readonly "previous_observation_digest": string | null;
  readonly "project_key": "ctower";
  readonly "reason_code": "no_scoped_append" | "scoped_row_appended" | "truncated_row" | "inode_replaced" | "file_truncated" | "unreadable_gap" | "classifier_unknown" | "monitor_interval_missing" | "registry_mismatch" | "observation_stale" | "observation_from_future" | "offset_reversed" | "pointer_mismatch";
  readonly "registry_digest": string;
  readonly "registry_id": string;
  readonly "registry_revision": number;
  readonly "run_id": string;
  readonly "schema": "ctower.ctower-project-fence-observation/v2";
  readonly "sequence": number;
  readonly "source_pointer_digest": string;
  readonly "status": "clear" | "detected" | "unknown";
  readonly "tenant_key": "ctower";
  readonly "to_offset": number;
}>;

export type CtowerProjectImportBatchRequest = Readonly<{
  readonly "batch_digest": string;
  readonly "batch_index": number;
  readonly "cutover_id": string;
  readonly "operations": ReadonlyArray<CtowerProjectImportOperation>;
  readonly "run_id": string;
  readonly "schema": "ctower.ctower-project-import-batch/v1";
}>;

export type CtowerProjectImportBatchResult = Readonly<{
  readonly "accepted_position": number | null;
  readonly "batch_digest": string;
  readonly "batch_index": number;
  readonly "durability_state": DurabilityState;
  readonly "projection_watermark": number;
  readonly "record_watermark": number;
  readonly "results": ReadonlyArray<MigrationImportOperationResult>;
  readonly "run_id": string;
}>;

export type CtowerProjectImportCorrectionRequest = Readonly<{
  readonly "correction_id": string;
  readonly "correction_kind": "alias" | "source_link" | "relation";
  readonly "cutover_id": string;
  readonly "expected_current_digest": string;
  readonly "project_key": "ctower";
  readonly "reason": string;
  readonly "replacement": MigrationCorrectionReplacement;
  readonly "reviewer_id": string;
  readonly "run_id": string;
  readonly "schema": "ctower.ctower-project-import-correction/v1";
  readonly "superseded_revision": MigrationCorrectionRevision;
  readonly "tenant_key": "ctower";
}>;

export type CtowerProjectImportFinalizeRequest = Readonly<{
  readonly "cutover_id": string;
  readonly "expected_run_semantic_digest": string;
  readonly "reconciliation_artifact": string;
  readonly "run_id": string;
}>;

export type CtowerProjectImportOperation = CtowerProjectTicketSeedOperation | CtowerProjectExactAliasOperation | CtowerProjectTicketRelationOperation | CtowerProjectSourceLinkOperation;

export type CtowerProjectImportRun = Readonly<{
  readonly "accepted_position": number | null;
  readonly "conservation": MigrationConservation | null;
  readonly "counts": MigrationImportCounts;
  readonly "cutover_id": string;
  readonly "dispositions": MigrationDispositions | null;
  readonly "durability_state": DurabilityState;
  readonly "export_native_watermark": number;
  readonly "importer_binding": MigrationImporterBinding;
  readonly "pass_two_measurement": MigrationPassTwoMeasurement | null;
  readonly "pinned_digests": MigrationPinnedDigests;
  readonly "project_key": "ctower";
  readonly "projection_watermark": number;
  readonly "reconciliation_graph": MigrationReconciliationGraph | null;
  readonly "record_watermark": number;
  readonly "refusals": ReadonlyArray<MigrationRefusal>;
  readonly "reviewer_key": MigrationReviewerKey;
  readonly "run_id": string;
  readonly "schema": "ctower.ctower-project-import-run/v2";
  readonly "semantic_digest": string;
  readonly "source_native_watermark": number;
  readonly "state": "created" | "export_equality_bound" | "alias_plan_bound" | "importing" | "pass_one_complete" | "pass_two_started" | "pass_two_noop" | "reconciled";
  readonly "tenant_key": "ctower";
}>;

export type CtowerProjectImportRunCreateRequest = Readonly<{
  readonly "build_digest": string;
  readonly "client_digest": string;
  readonly "cutover_id": string;
  readonly "importer_credential_digest": string;
  readonly "importer_expires_at": string;
  readonly "operation_registry_digest": string;
  readonly "project_key": "ctower";
  readonly "reviewer_key_ref": string;
  readonly "reviewer_key_version": number;
  readonly "reviewer_public_key_digest": string;
  readonly "schema_digest": string;
  readonly "source_selection_artifact": string;
  readonly "source_selection_digest": string;
  readonly "tenant_key": "ctower";
}>;

export type CtowerProjectMigrationReceipt = Readonly<{
  readonly "accepted_position": number | null;
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "object_id": string;
  readonly "record_position": number;
  readonly "revision": number;
  readonly "semantic_digest": string;
}>;

export type CtowerProjectReconciliationResult = Readonly<{
  readonly "accepted_position": number | null;
  readonly "actual_graph": MigrationReconciliationGraph;
  readonly "cutover_id": string;
  readonly "durability_state": DurabilityState;
  readonly "expected_graph": MigrationReconciliationGraph;
  readonly "pass_two_measurement": MigrationPassTwoMeasurement;
  readonly "pinned_digests": MigrationPinnedDigests;
  readonly "project_key": "ctower";
  readonly "reconciled_at": string;
  readonly "reconciliation_id": string;
  readonly "report_digest": string;
  readonly "review": MigrationReview;
  readonly "reviewer_key": MigrationReviewerKey;
  readonly "run_id": string;
  readonly "schema": "ctower.ctower-project-reconciliation/v2";
  readonly "signature": MigrationDetachedSignature;
  readonly "target_semantic_digest": string;
  readonly "watermarks": MigrationWatermarks;
}>;

export type CtowerProjectSourceLinkOperation = Readonly<{
  readonly "identity": MigrationOperationIdentity;
  readonly "link_class": "decision" | "external_effect" | "artifact_not_proof" | "provenance";
  readonly "linked_not_proof": true;
  readonly "operation": "source_link";
  readonly "project_key": "ctower";
  readonly "reason_code": string;
  readonly "source": MigrationSourceIdentity;
  readonly "target_id": string;
  readonly "target_kind": "ticket" | "ticket_relation" | "checkpoint" | "decision" | "artifact" | "external_effect";
}>;

export type CtowerProjectTicketRelationOperation = Readonly<{
  readonly "identity": MigrationOperationIdentity;
  readonly "operation": "ticket_relation";
  readonly "project_key": "ctower";
  readonly "reason": string;
  readonly "relation_id": string;
  readonly "relation_kind": "parent_of" | "depends_on" | "blocks" | "duplicates" | "relates_to" | "caused_by";
  readonly "source_ticket_id": string;
  readonly "target_ticket_id": string;
}>;

export type CtowerProjectTicketSeedOperation = Readonly<{
  readonly "identity": MigrationOperationIdentity;
  readonly "initial_commander_custodian_id": string;
  readonly "operation": "ticket_seed";
  readonly "priority": "P2";
  readonly "project_key": "ctower";
  readonly "source": MigrationSourceIdentity;
  readonly "title": string;
}>;

export type CustodyTransferRequest = Readonly<{
  readonly "expected_version": number;
  readonly "from_custodian_id": string;
  readonly "protected_transfer": boolean;
  readonly "reason": string;
  readonly "to_custodian_id": string;
}>;

export type CustodyTransferredAuditEvent = Readonly<{
  readonly "actor_principal_id": string;
  readonly "command_id": string;
  readonly "event_hash": string;
  readonly "event_id": string;
  readonly "kind": "ticket.custody_transferred";
  readonly "occurred_at": string;
  readonly "payload": CustodyTransferredPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type CustodyTransferredPayload = Readonly<{
  readonly "from_custodian_id": string;
  readonly "reason": string;
  readonly "to_custodian_id": string;
}>;

export type DeferIntent = Readonly<{
  readonly "expected_version": number;
  readonly "kind": "defer";
  readonly "reason": string;
  readonly "review_after": string;
}>;

export type DeferredAuditData = Readonly<{
  readonly "episode_number": number;
  readonly "reason": string;
  readonly "review_after": string;
}>;

export type DurabilityState = "durability_pending" | "accepted";

export type EvidenceRequest = Readonly<{
  readonly "artifact_digest": string;
  readonly "candidate_digest"?: string | null;
  readonly "content": string;
  readonly "criterion_key": string;
  readonly "evidence_id": string;
  readonly "expected_version": number;
}>;

export type FreezeCriteriaRequest = Readonly<{
  readonly "candidate_digest": string;
  readonly "criteria": ReadonlyArray<ProofCriterion>;
  readonly "expected_version": number;
}>;

export type HealthContributor = Readonly<{
  readonly "key": HealthContributorKey;
  readonly "observed_at": string;
  readonly "owner": string;
  readonly "reason": string;
  readonly "status": HealthStatus;
  readonly "threshold_seconds": number;
  readonly "watermark": number | null;
}>;

export type HealthContributorKey = "durability" | "scheduler" | "outbox" | "projection" | "backup" | "anchor" | "object" | "synthetic";

export type HealthDimension = Readonly<{
  readonly "contributors": ReadonlyArray<HealthContributor>;
  readonly "status": HealthStatus;
}>;

export type HealthStatus = "HEALTHY" | "DEGRADED" | "STATE_UNKNOWN";

export type IntakeCommandResult = Readonly<{
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "inbound_event_id": string;
  readonly "outcome": IntakeOutcome;
  readonly "project_key": string;
  readonly "quarantine_reason": string | null;
  readonly "source": SourceReference;
  readonly "thread_id": string;
  readonly "thread_version": number;
  readonly "ticket_id": string | null;
  readonly "ticket_version": number | null;
}>;

export type IntakeIntent = "discussion" | "create_ticket" | "link_ticket";

export type IntakeOutcome = "discussion" | "ticket_created" | "ticket_linked" | "quarantined";

export type IntakePromotionIntent = "create_ticket" | "link_ticket";

export type IntakePromotionRequest = Readonly<{
  readonly "expected_thread_version": number;
  readonly "expected_ticket_version"?: number | null;
  readonly "initial_custodian_id"?: string | null;
  readonly "intent": IntakePromotionIntent;
  readonly "priority"?: Priority | null;
  readonly "target_ticket_id"?: string | null;
  readonly "title"?: string | null;
}>;

export type IntakeSubmitRequest = Readonly<{
  readonly "content": string;
  readonly "expected_thread_version"?: number | null;
  readonly "expected_ticket_version"?: number | null;
  readonly "initial_custodian_id"?: string | null;
  readonly "intent"?: IntakeIntent;
  readonly "priority"?: Priority | null;
  readonly "project_key": string;
  readonly "source": SourceReference;
  readonly "taint"?: IntakeTaint;
  readonly "target_ticket_id"?: string | null;
  readonly "thread_id"?: string | null;
  readonly "title"?: string | null;
}>;

export type IntakeTaint = "authenticated" | "external_untrusted" | "quarantine_required";

export type MigrationAliasCorrection = Readonly<{
  readonly "disposition": "alias_linked_existing" | "exact_duplicate" | "provenance_only";
  readonly "kind": "alias";
  readonly "target_ticket_id": string;
}>;

export type MigrationConservation = Readonly<{
  readonly "alias_forks_or_cycles": 0;
  readonly "checkpoint_definitions": 14;
  readonly "forbidden_data_items": 0;
  readonly "forbidden_relation_cycles": 0;
  readonly "missing_relation_endpoints": 0;
  readonly "pass_two_new_domain_facts": 0;
  readonly "pass_two_new_events": 0;
  readonly "pass_two_new_outbox_rows": 0;
  readonly "pass_two_projection_semantic_delta": 0;
  readonly "pass_two_record_position_delta": 0;
  readonly "selected_logical_items": number;
  readonly "selected_request_logical": 86;
  readonly "selected_request_physical_snapshots": 243;
  readonly "stable_aliases": 27;
  readonly "unexpected_sources": 0;
  readonly "unresolved_active_claims": 0;
  readonly "unresolved_aliases": 0;
}>;

export type MigrationCorrectionReplacement = MigrationAliasCorrection | MigrationSourceLinkCorrection | MigrationRelationCorrection;

export type MigrationCorrectionRevision = Readonly<{
  readonly "object_id": string;
  readonly "revision": number;
}>;

export type MigrationDetachedSignature = Readonly<{
  readonly "algorithm": "Ed25519";
  readonly "key_ref": string;
  readonly "key_version": number;
  readonly "public_key_digest": string;
  readonly "signature": string;
  readonly "signed_digest": string;
}>;

export type MigrationDispositions = Readonly<{
  readonly "alias_linked_existing": number;
  readonly "artifact_linked_not_proof": number;
  readonly "attention_required": 0;
  readonly "created_ticket": number;
  readonly "decision_link": number;
  readonly "exact_duplicate": number;
  readonly "excluded_out_of_scope": number;
  readonly "external_effect_link": number;
  readonly "project_checkpoint_definition": number;
  readonly "provenance_only": number;
}>;

export type MigrationFenceFileIdentity = Readonly<{
  readonly "device": number;
  readonly "inode": number;
  readonly "scoped_rows_digest": string;
}>;

export type MigrationHealthDigests = Readonly<{
  readonly "alias_map": string | null;
  readonly "export_equality": string | null;
  readonly "fence_observation": string | null;
  readonly "fence_registry": string | null;
  readonly "reconciliation": string | null;
  readonly "source_selection": string | null;
}>;

export type MigrationImportCounts = Readonly<{
  readonly "applied_operations": number;
  readonly "planned_operations": number;
  readonly "refused_operations": number;
  readonly "replayed_operations": number;
}>;

export type MigrationImportOperationResult = Readonly<{
  readonly "command_id": string;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "occurred_at": string;
  readonly "operation_kind": "ticket_seed" | "exact_alias" | "ticket_relation" | "source_link";
  readonly "record_position": number;
  readonly "replayed": boolean;
  readonly "target_id": string;
}>;

export type MigrationImporterBinding = Readonly<{
  readonly "credential_digest": string;
  readonly "expires_at": string;
  readonly "principal_kind": "migration_importer";
  readonly "revoked": boolean;
}>;

export type MigrationOperationIdentity = Readonly<{
  readonly "command_id": string;
  readonly "immutable_source_id": string;
  readonly "namespace": string;
  readonly "operation_kind": "ticket_seed" | "exact_alias" | "ticket_relation" | "source_link";
  readonly "planned_target_ref": string;
  readonly "source_version_or_digest": string;
}>;

export type MigrationPassTwoMeasurement = Readonly<{
  readonly "end_domain_facts": number;
  readonly "end_events": number;
  readonly "end_outbox_rows": number;
  readonly "end_project_delivery_digest": string;
  readonly "end_record_position": number;
  readonly "end_snapshot_digest": string;
  readonly "new_domain_facts": 0;
  readonly "new_events": 0;
  readonly "new_outbox_rows": 0;
  readonly "projection_semantic_delta": 0;
  readonly "record_position_delta": 0;
  readonly "start_domain_facts": number;
  readonly "start_events": number;
  readonly "start_outbox_rows": number;
  readonly "start_project_delivery_digest": string;
  readonly "start_record_position": number;
  readonly "start_snapshot_digest": string;
}>;

export type MigrationPinnedDigests = Readonly<{
  readonly "alias_map": string | null;
  readonly "build": string;
  readonly "client": string;
  readonly "export_equality": string | null;
  readonly "fence_registry": string | null;
  readonly "import_plan": string | null;
  readonly "operation_registry": string;
  readonly "reviewer_public_key": string;
  readonly "schema": string;
  readonly "source_selection": string;
}>;

export type MigrationReconciliationGraph = Readonly<{
  readonly "active_claims": ReadonlyArray<string>;
  readonly "alias_revisions": ReadonlyArray<string>;
  readonly "checkpoint_criteria": ReadonlyArray<string>;
  readonly "checkpoint_definitions": ReadonlyArray<string>;
  readonly "custody_intervals": ReadonlyArray<string>;
  readonly "cycles": ReadonlyArray<string>;
  readonly "events": ReadonlyArray<string>;
  readonly "forbidden": ReadonlyArray<string>;
  readonly "graph_digest": string;
  readonly "lifecycle_facts": ReadonlyArray<string>;
  readonly "operation_identities": ReadonlyArray<string>;
  readonly "operation_results": ReadonlyArray<string>;
  readonly "outbox_rows": ReadonlyArray<string>;
  readonly "priority_facts": ReadonlyArray<string>;
  readonly "project_delivery_rows": ReadonlyArray<string>;
  readonly "relation_endpoints": ReadonlyArray<string>;
  readonly "relations": ReadonlyArray<string>;
  readonly "source_links": ReadonlyArray<string>;
  readonly "stable_aliases": ReadonlyArray<string>;
  readonly "tickets": ReadonlyArray<string>;
  readonly "unexpected": ReadonlyArray<string>;
  readonly "unresolved": ReadonlyArray<string>;
}>;

export type MigrationRefusal = Readonly<{
  readonly "code": string;
  readonly "operation_identity": string;
}>;

export type MigrationRelationCorrection = Readonly<{
  readonly "kind": "relation";
  readonly "replacement_relation_id": string | null;
  readonly "superseded_relation_active": false;
}>;

export type MigrationReview = Readonly<{
  readonly "decision": "approved";
  readonly "reviewed_at": string;
  readonly "reviewer_principal_id": string;
}>;

export type MigrationReviewerKey = Readonly<{
  readonly "key_version": number;
  readonly "public_key_digest": string;
  readonly "public_key_ref": string;
}>;

export type MigrationSourceIdentity = Readonly<{
  readonly "immutable_source_id": string;
  readonly "namespace": string;
  readonly "source_digest": string;
  readonly "source_version": string;
}>;

export type MigrationSourceLinkCorrection = Readonly<{
  readonly "disposition": "decision_link" | "external_effect_link" | "artifact_linked_not_proof" | "provenance_only" | "excluded_out_of_scope";
  readonly "kind": "source_link";
  readonly "target_id": string;
  readonly "target_kind": "ticket" | "ticket_relation" | "checkpoint" | "decision" | "artifact" | "external_effect";
}>;

export type MigrationWatermarks = Readonly<{
  readonly "export_native": number;
  readonly "projection_position": number;
  readonly "record_position": number;
  readonly "source_native": number;
}>;

export type MutableAssignmentKind = "current_assignee" | "stage_owner" | "reviewer_assignment";

export type PoisonDispositionAction = "retry" | "tombstone";

export type PoisonDispositionReceipt = Readonly<{
  readonly "action": PoisonDispositionAction;
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "outbox_id": string;
  readonly "recorded_at": string;
}>;

export type PoisonDispositionRequest = Readonly<{
  readonly "action": PoisonDispositionAction;
  readonly "consumer_key": string;
  readonly "reason": string;
  readonly "topic": string;
}>;

export type Priority = "P0" | "P1" | "P2";

export type PriorityChangeRequest = Readonly<{
  readonly "expected_version": number;
  readonly "priority": Priority;
  readonly "reason": string;
  readonly "urgent_evidence_ref"?: string | null;
}>;

export type PriorityChangedAuditData = Readonly<{
  readonly "authority": "commander" | "operator";
  readonly "from_priority": Priority;
  readonly "policy_ref": "ctower.priority-authority@1";
  readonly "reason": string;
  readonly "to_priority": Priority;
  readonly "urgent_evidence_ref": string | null;
}>;

export type Problem = Readonly<{
  readonly "code": "bootstrap-consumed" | "bootstrap-expired" | "bootstrap-nonempty" | "bootstrap-origin" | "bundle-base-conflict" | "bundle-compatibility-refused" | "bundle-digest-mismatch" | "bundle-grant-refused" | "bundle-independence-refused" | "bundle-no-effect-refused" | "bundle-not-active" | "bundle-plan-mismatch" | "bundle-recovery-unavailable" | "bundle-reference-invalid" | "bundle-schema-invalid" | "bundle-security-refused" | "durability_pending" | "i1-7c-required" | "idempotency-conflict" | "intake-already-promoted" | "intake-promotion-ineligible" | "intake-source-project-mismatch" | "intake-source-conflict" | "migration-alias-conflict" | "migration-capability-denied" | "migration-correction-conflict" | "migration-digest-mismatch" | "migration-export-nondeterminism" | "migration-fence-detected" | "migration-import-finalization-refused" | "migration-operation-drift" | "migration-relation-invalid" | "migration-run-conflict" | "migration-signature-invalid" | "migration-source-selection-drift" | "migration-source-tainted" | "poison-not-found" | "project-scope-denied" | "project-delivery-unavailable" | "request-body-too-large" | "proof-candidate-author-mismatch" | "proof-candidate-digest-invalid" | "proof-candidate-digest-not-current" | "proof-candidate-unchanged" | "proof-criteria-already-frozen" | "proof-criteria-invalid" | "proof-criteria-policy-mismatch" | "proof-criterion-unknown" | "proof-current-evidence-missing" | "proof-evidence-digest-mismatch" | "proof-evidence-id-conflict" | "proof-protected-authority-required" | "proof-policy-mismatch" | "proof-policy-pin-mismatch" | "proof-self-review-refused" | "proof-verdict-id-conflict" | "tenant-scope-denied" | "ticket-comment-ineligible" | "ticket-comment-invalid" | "unauthorized" | "validation-error" | "version-conflict" | "work-assignment-kind-refused" | "work-assignment-target-ineligible" | "work-assignment-unchanged" | "work-priority-unchanged" | "work-blocker-already-resolved" | "work-blocker-id-conflict" | "work-blocker-owner-ineligible" | "work-blocker-unknown" | "work-intent-unmet" | "work-relation-cycle" | "work-relation-exists" | "work-reopen-unmet" | "work-ticket-terminal" | "workflow-already-started" | "workflow-pin-mismatch" | "workflow-predicate-unsatisfied" | "workflow-run-not-started" | "proof-incomplete" | "workflow-state-conflict" | "workflow-terminal" | "workflow-transition-not-declared" | "workflow-version-unknown" | "workflow-not-terminal";
  readonly "command_id"?: string | null;
  readonly "current_version"?: number | null;
  readonly "detail": string;
  readonly "status": number;
  readonly "title": string;
  readonly "type": string;
  readonly "unmet_facts"?: ReadonlyArray<string>;
}>;

export type ProjectCustodyTransferredEvent = Readonly<{
  readonly "acceptance_position": number;
  readonly "actor_principal_id": string;
  readonly "aggregate_id": string;
  readonly "client_command_id": string;
  readonly "event_id": string;
  readonly "kind": "ticket.custody_transferred";
  readonly "occurred_at": string;
  readonly "payload": CustodyTransferredPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type ProjectDeliveryCriteria = Readonly<{
  readonly "declared": number;
  readonly "proven": number;
}>;

export type ProjectDeliveryRow = Readonly<{
  readonly "accountable_owner": string;
  readonly "checkpoint_key": string;
  readonly "checkpoint_label": string;
  readonly "confidence": "development_degraded" | "disaster_safe" | "STATE_UNKNOWN";
  readonly "criteria": ProjectDeliveryCriteria;
  readonly "data_class": "RECONSTRUCTIBLE_ONLY" | "DISASTER_SAFE_CTOWER_ENGINEERING" | "STATE_UNKNOWN";
  readonly "derivation_reasons": ReadonlyArray<string>;
  readonly "durability": "CP3_D_NOT_PROVEN" | "CP3_D_PROVEN" | "STATE_UNKNOWN";
  readonly "freshness": "fresh" | "stale" | "STATE_UNKNOWN";
  readonly "freshness_due_at": string;
  readonly "headline_state": "planned" | "in_progress" | "ready_to_land" | "merged" | "verified" | "released" | "blocked" | "done";
  readonly "health": "CP3_D_NOT_PROVEN" | "CURRENT" | "STATE_UNKNOWN";
  readonly "outcome": string;
  readonly "projection_watermark": number;
  readonly "qualifying_stage_slots_filled": number;
  readonly "qualifying_stage_slots_required": number;
  readonly "qualifying_stage_unfilled_or_unknown_slot_keys": ReadonlyArray<string>;
  readonly "rebuild_generation": number;
  readonly "reconciled_at": string;
  readonly "recovery": "EXTERNAL_FAILURE_DOMAIN_UNPROVEN" | "EXTERNAL_FAILURE_DOMAIN_PROVEN" | "STATE_UNKNOWN";
  readonly "semantic_digest": string;
  readonly "source_ids": ReadonlyArray<string>;
  readonly "source_watermark": number;
  readonly "underlying_maturity": "planned" | "in_progress" | "ready_to_land" | "merged" | "verified" | "released";
}>;

export type ProjectDeliveryView = Readonly<{
  readonly "company_key": string;
  readonly "freshness_due_at": string;
  readonly "project_key": string;
  readonly "projection_record_position": number;
  readonly "projection_semantic_digest": string;
  readonly "rebuild_generation": number;
  readonly "reconciled_at": string;
  readonly "rows": ReadonlyArray<ProjectDeliveryRow>;
  readonly "schema": "ctower.project-delivery/v1";
  readonly "source_record_position": number;
}>;

export type ProjectEvent = ProjectTicketCreatedEvent | ProjectCustodyTransferredEvent | ProjectTicketCommentAddedEvent | ProjectWorkChangedEvent | ProjectWorkflowChangedEvent | ProjectProofChangedEvent;

export type ProjectEventPage = Readonly<{
  readonly "events": ReadonlyArray<ProjectEvent>;
  readonly "has_more": boolean;
  readonly "next_cursor": string;
  readonly "project_key": string;
  readonly "source_watermark": number;
}>;

export type ProjectProofChangedEvent = Readonly<{
  readonly "acceptance_position": number;
  readonly "actor_principal_id": string;
  readonly "aggregate_id": string;
  readonly "client_command_id": string;
  readonly "event_id": string;
  readonly "kind": "proof.changed";
  readonly "occurred_at": string;
  readonly "payload": ProofChangedAuditPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type ProjectTicketCommentAddedEvent = Readonly<{
  readonly "acceptance_position": number;
  readonly "actor_principal_id": string;
  readonly "aggregate_id": string;
  readonly "client_command_id": string;
  readonly "event_id": string;
  readonly "kind": "ticket.comment_added";
  readonly "occurred_at": string;
  readonly "payload": TicketCommentAddedPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type ProjectTicketCreatedEvent = Readonly<{
  readonly "acceptance_position": number;
  readonly "actor_principal_id": string;
  readonly "aggregate_id": string;
  readonly "client_command_id": string;
  readonly "event_id": string;
  readonly "kind": "ticket.created";
  readonly "occurred_at": string;
  readonly "payload": TicketCreatedPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type ProjectWorkChangedEvent = Readonly<{
  readonly "acceptance_position": number;
  readonly "actor_principal_id": string;
  readonly "aggregate_id": string;
  readonly "client_command_id": string;
  readonly "event_id": string;
  readonly "kind": "work.changed";
  readonly "occurred_at": string;
  readonly "payload": WorkChangedAuditPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type ProjectWorkflowChangedEvent = Readonly<{
  readonly "acceptance_position": number;
  readonly "actor_principal_id": string;
  readonly "aggregate_id": string;
  readonly "client_command_id": string;
  readonly "event_id": string;
  readonly "kind": "workflow.changed";
  readonly "occurred_at": string;
  readonly "payload": WorkflowChangedAuditPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type ProjectionHealth = "CURRENT" | "STATE_UNKNOWN";

export type ProofChangedAuditEvent = Readonly<{
  readonly "actor_principal_id": string;
  readonly "command_id": string;
  readonly "event_hash": string;
  readonly "event_id": string;
  readonly "kind": "proof.changed";
  readonly "occurred_at": string;
  readonly "payload": ProofChangedAuditPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type ProofChangedAuditPayload = Readonly<{
  readonly "candidate_digest": string;
  readonly "invalidated_evidence_ids": ReadonlyArray<string>;
  readonly "invalidated_verdict_ids": ReadonlyArray<string>;
  readonly "operation": "freeze_criteria" | "record_evidence" | "record_verdict" | "change_candidate";
  readonly "proof_version": number;
  readonly "ticket_id": string;
}>;

export type ProofCriterion = Readonly<{
  readonly "candidate_dependent": boolean;
  readonly "description": string;
  readonly "key": string;
  readonly "requires_verdict": boolean;
}>;

export type ProofReceipt = Readonly<{
  readonly "artifact_digest": string | null;
  readonly "candidate_digest": string;
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "invalidated_evidence_ids": ReadonlyArray<string>;
  readonly "invalidated_verdict_ids": ReadonlyArray<string>;
  readonly "proof_id": string;
  readonly "satisfied": boolean;
  readonly "ticket_id": string;
  readonly "version": number;
}>;

export type RelationAddedAuditData = Readonly<{
  readonly "reason": string;
  readonly "relation_kind": "parent_of" | "depends_on" | "blocks" | "duplicates" | "relates_to" | "caused_by";
  readonly "target_ticket_id": string;
}>;

export type RelationKind = "parent_of" | "depends_on" | "blocks" | "duplicates" | "relates_to" | "caused_by";

export type RelationRequest = Readonly<{
  readonly "expected_version": number;
  readonly "reason": string;
  readonly "relation_kind": RelationKind;
  readonly "target_ticket_id": string;
}>;

export type ReopenIntent = Readonly<{
  readonly "expected_version": number;
  readonly "kind": "reopen";
  readonly "priority_policy": "carry_forward";
  readonly "reason": string;
}>;

export type ReopenedAuditData = Readonly<{
  readonly "episode_number": number;
  readonly "priority": Priority;
  readonly "reason": string;
}>;

export type ResolveCloseRequest = Readonly<{
  readonly "expected_version": number;
  readonly "workflow_ref"?: string | null;
}>;

export type SecretBindingReference = Readonly<{
  readonly "name": string;
  readonly "reference_class": "os-credential" | "vault-path" | "runtime-binding";
}>;

export type SourceReference = Readonly<{
  readonly "kind": string;
  readonly "ref": string;
}>;

export type SyntheticRunReceipt = Readonly<{
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "job_id": string;
  readonly "run_id": string;
  readonly "workflow_ref": "ctower.trust-spine-four-stage@1";
}>;

export type SyntheticRunRequest = Readonly<{
  readonly "workflow_ref": "ctower.trust-spine-four-stage@1";
}>;

export type SyntheticRunResource = Readonly<{
  readonly "attempt_count": number;
  readonly "completed_at": string | null;
  readonly "created_at": string;
  readonly "detail_code": string | null;
  readonly "job_id": string;
  readonly "lifecycle_facts": ReadonlyArray<"resolved" | "closed">;
  readonly "run_id": string;
  readonly "state": SyntheticRunState;
  readonly "ticket_id": string | null;
  readonly "workflow_ref": "ctower.trust-spine-four-stage@1";
}>;

export type SyntheticRunState = "pending" | "running" | "succeeded" | "failed";

export type TelemetryContext = Readonly<{
  readonly "actor_id": string;
  readonly "causation_id": string;
  readonly "command_id": string;
  readonly "component_revision_id"?: string | null;
  readonly "correlation_id": string;
  readonly "deployment_id"?: string | null;
  readonly "effect_id"?: string | null;
  readonly "fencing_token"?: number | null;
  readonly "job_id"?: string | null;
  readonly "runner_id"?: string | null;
  readonly "schema": "ctower.telemetry-context/v1";
  readonly "span_id": string;
  readonly "stage_attempt_id"?: string | null;
  readonly "tenant_id": string;
  readonly "ticket_id"?: string | null;
  readonly "trace_flags": number;
  readonly "trace_id": string;
  readonly "trace_state"?: string | null;
  readonly "workflow_run_id"?: string | null;
}>;

export type TicketCommandResult = Readonly<{
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "ticket": TicketResource;
}>;

export type TicketCommentAddedAuditEvent = Readonly<{
  readonly "actor_principal_id": string;
  readonly "command_id": string;
  readonly "event_hash": string;
  readonly "event_id": string;
  readonly "kind": "ticket.comment_added";
  readonly "occurred_at": string;
  readonly "payload": TicketCommentAddedPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type TicketCommentAddedPayload = Readonly<{
  readonly "body": string;
  readonly "comment_id": string;
  readonly "ticket_id": string;
}>;

export type TicketCommentRequest = Readonly<{
  readonly "body": string;
}>;

export type TicketCommentResult = Readonly<{
  readonly "command_id": string;
  readonly "comment_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_id": string;
  readonly "ticket_id": string;
}>;

export type TicketCreateRequest = Readonly<{
  readonly "initial_custodian_id"?: string | null;
  readonly "priority": Priority;
  readonly "project_key": string;
  readonly "source": SourceReference;
  readonly "title": string;
}>;

export type TicketCreatedAuditEvent = Readonly<{
  readonly "actor_principal_id": string;
  readonly "command_id": string;
  readonly "event_hash": string;
  readonly "event_id": string;
  readonly "kind": "ticket.created";
  readonly "occurred_at": string;
  readonly "payload": TicketCreatedPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type TicketCreatedPayload = Readonly<{
  readonly "custodian_id": string;
  readonly "priority": Priority;
  readonly "project_key"?: string;
  readonly "source_kind": string;
  readonly "source_ref": string;
  readonly "title": string;
}>;

export type TicketIntentRequest = Readonly<{
  readonly "intent": AdmitIntent | DeferIntent | BlockIntent | UnblockIntent | ReopenIntent;
}>;

export type TicketResource = Readonly<{
  readonly "created_at": string;
  readonly "custodian_id": string;
  readonly "durability_state": DurabilityState;
  readonly "priority": Priority;
  readonly "source": SourceReference;
  readonly "ticket_id": string;
  readonly "title": string;
  readonly "version": number;
}>;

export type TimelineEvent = Readonly<{
  readonly "actor_principal_id": string;
  readonly "command_id": string;
  readonly "event_id": string;
  readonly "kind": "ticket.created" | "ticket.custody_transferred" | "ticket.comment_added";
  readonly "occurred_at": string;
  readonly "payload": TicketCreatedPayload | CustodyTransferredPayload | TicketCommentAddedPayload;
  readonly "sequence": number;
}>;

export type TimelineResponse = Readonly<{
  readonly "durability_state": DurabilityState;
  readonly "events": ReadonlyArray<TimelineEvent>;
  readonly "ticket_id": string;
}>;

export type UnblockIntent = Readonly<{
  readonly "blocker_id": string;
  readonly "expected_version": number;
  readonly "kind": "unblock";
  readonly "reason": string;
  readonly "resolution_evidence_ref": string;
}>;

export type VerdictDecision = "pass" | "fail";

export type VerdictRequest = Readonly<{
  readonly "candidate_digest"?: string | null;
  readonly "criterion_key": string;
  readonly "decision": VerdictDecision;
  readonly "expected_version": number;
  readonly "verdict_id": string;
}>;

export type VersionedComponent = Readonly<{
  readonly "compatibility": ComponentCompatibility;
  readonly "content_digest": string;
  readonly "key": string;
  readonly "kind": ComponentKind;
  readonly "lifecycle": "draft" | "published" | "deprecated" | "revoked";
  readonly "payload_ref": string;
  readonly "provenance": ReadonlyArray<ComponentProvenance>;
  readonly "revision": number;
  readonly "schema": "ctower.versioned-component/v1";
  readonly "schema_ref": string;
  readonly "scope": ComponentScope;
  readonly "supersedes"?: ComponentReference;
}>;

export type WorkAdmittedAuditPayload = Readonly<{
  readonly "data": AdmittedAuditData;
  readonly "operation": "admitted";
  readonly "ticket_id": string;
  readonly "work_version": number;
}>;

export type WorkAssignmentChangedAuditPayload = Readonly<{
  readonly "data": AssignmentChangedAuditData;
  readonly "operation": "assignment_changed";
  readonly "ticket_id": string;
  readonly "work_version": number;
}>;

export type WorkBlockerOpenedAuditPayload = Readonly<{
  readonly "data": BlockerOpenedAuditData;
  readonly "operation": "blocker_opened";
  readonly "ticket_id": string;
  readonly "work_version": number;
}>;

export type WorkBlockerResolvedAuditPayload = Readonly<{
  readonly "data": BlockerResolvedAuditData;
  readonly "operation": "blocker_resolved";
  readonly "ticket_id": string;
  readonly "work_version": number;
}>;

export type WorkChangedAuditEvent = Readonly<{
  readonly "actor_principal_id": string;
  readonly "command_id": string;
  readonly "event_hash": string;
  readonly "event_id": string;
  readonly "kind": "work.changed";
  readonly "occurred_at": string;
  readonly "payload": WorkChangedAuditPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type WorkChangedAuditPayload = WorkPriorityChangedAuditPayload | WorkAssignmentChangedAuditPayload | WorkAdmittedAuditPayload | WorkDeferredAuditPayload | WorkBlockerOpenedAuditPayload | WorkBlockerResolvedAuditPayload | WorkReopenedAuditPayload | WorkRelationAddedAuditPayload;

export type WorkDeferredAuditPayload = Readonly<{
  readonly "data": DeferredAuditData;
  readonly "operation": "deferred";
  readonly "ticket_id": string;
  readonly "work_version": number;
}>;

export type WorkPriorityChangedAuditPayload = Readonly<{
  readonly "data": PriorityChangedAuditData;
  readonly "operation": "priority_changed";
  readonly "ticket_id": string;
  readonly "work_version": number;
}>;

export type WorkReceipt = Readonly<{
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "operation": "priority_changed" | "assignment_changed" | "admitted" | "deferred" | "blocker_opened" | "blocker_resolved" | "reopened" | "relation_added";
  readonly "ticket_id": string;
  readonly "version": number;
}>;

export type WorkRelationAddedAuditPayload = Readonly<{
  readonly "data": RelationAddedAuditData;
  readonly "operation": "relation_added";
  readonly "ticket_id": string;
  readonly "work_version": number;
}>;

export type WorkReopenedAuditPayload = Readonly<{
  readonly "data": ReopenedAuditData;
  readonly "operation": "reopened";
  readonly "ticket_id": string;
  readonly "work_version": number;
}>;

export type WorkflowChangedAuditEvent = Readonly<{
  readonly "actor_principal_id": string;
  readonly "command_id": string;
  readonly "event_hash": string;
  readonly "event_id": string;
  readonly "kind": "workflow.changed";
  readonly "occurred_at": string;
  readonly "payload": WorkflowChangedAuditPayload;
  readonly "record_position": number;
  readonly "sequence": number;
  readonly "stream_id": string;
}>;

export type WorkflowChangedAuditPayload = Readonly<{
  readonly "lifecycle_facts": ReadonlyArray<"resolved" | "closed">;
  readonly "operation": "start" | "transition" | "resolve_close";
  readonly "stage": string;
  readonly "ticket_id": string;
  readonly "workflow_ref": string;
  readonly "workflow_version": number;
}>;

export type WorkflowReceipt = Readonly<{
  readonly "activity_class": ActivityClass;
  readonly "command_id": string;
  readonly "durability_state": DurabilityState;
  readonly "event_ids": ReadonlyArray<string>;
  readonly "lifecycle_facts": ReadonlyArray<"resolved" | "closed">;
  readonly "stage": string;
  readonly "ticket_id": string;
  readonly "version": number;
  readonly "workflow_ref": string;
  readonly "workflow_run_id": string;
}>;

export type WorkflowStartRequest = Readonly<{
  readonly "evidence_policy_digest": string;
  readonly "evidence_policy_ref": string;
  readonly "execution_policy_digest": string;
  readonly "execution_policy_ref": string;
  readonly "gate_policy_digest": string;
  readonly "gate_policy_ref": string;
  readonly "workflow_digest": string;
  readonly "workflow_ref": string;
}>;

export type WorkflowTransitionRequest = Readonly<{
  readonly "destination_stage": string;
  readonly "expected_version": number;
  readonly "source_stage": string;
  readonly "workflow_ref": string;
}>;
