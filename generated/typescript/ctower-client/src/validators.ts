// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:54cf5b70505bad9fa5f66e98d01684513eb24d9be636f21eba42076daad4f9f0

import type { OperationId } from "./operations.js";
import type {
  JsonArrayNode,
  JsonNode,
  JsonNumberNode,
  JsonObjectNode,
} from "./response-json.js";

type SchemaObject = Readonly<Record<string, unknown>>;

const JSON_INTEGER_MINIMUM = -9007199254740991;
const JSON_INTEGER_MAXIMUM = 9007199254740991;
const SCHEMAS: SchemaObject = {"ActivityClass":{"enum":["work","verification"],"type":"string"},"AdmitIntent":{"additionalProperties":false,"properties":{"expected_version":{"minimum":1,"type":"integer"},"kind":{"const":"admit"},"reason":{"maxLength":500,"minLength":1,"type":"string"}},"required":["kind","expected_version","reason"],"type":"object"},"AdmittedAuditData":{"additionalProperties":false,"properties":{"episode_number":{"minimum":1,"type":"integer"},"reason":{"maxLength":500,"minLength":1,"type":"string"}},"required":["episode_number","reason"],"type":"object"},"AssignmentChangeRequest":{"additionalProperties":false,"properties":{"assignment_kind":{"$ref":"#/components/schemas/MutableAssignmentKind"},"expected_version":{"minimum":1,"type":"integer"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"scope_ref":{"maxLength":256,"minLength":1,"type":["string","null"]},"to_principal_id":{"format":"uuid","type":"string"}},"required":["assignment_kind","expected_version","reason","to_principal_id"],"type":"object"},"AssignmentChangedAuditData":{"additionalProperties":false,"properties":{"assignment_kind":{"enum":["current_assignee","stage_owner","reviewer_assignment"],"type":"string"},"from_principal_id":{"format":"uuid","type":["string","null"]},"reason":{"maxLength":500,"minLength":1,"type":"string"},"scope_ref":{"maxLength":256,"minLength":1,"type":["string","null"]},"to_principal_id":{"format":"uuid","type":"string"}},"required":["assignment_kind","from_principal_id","reason","scope_ref","to_principal_id"],"type":"object"},"AssignmentInterval":{"additionalProperties":false,"properties":{"assigned_at":{"format":"date-time","type":"string"},"assignment_kind":{"$ref":"#/components/schemas/AssignmentKind"},"changed_by":{"format":"uuid","type":"string"},"episode_number":{"minimum":1,"type":"integer"},"principal_id":{"format":"uuid","type":"string"},"reason":{"type":"string"},"released_at":{"format":"date-time","type":["string","null"]},"scope_ref":{"type":["string","null"]},"sequence":{"minimum":1,"type":"integer"}},"required":["assigned_at","assignment_kind","changed_by","episode_number","principal_id","reason","released_at","scope_ref","sequence"],"type":"object"},"AssignmentKind":{"enum":["ticket_custodian","current_assignee","stage_owner","reviewer_assignment","runner_lease_owner"],"type":"string"},"AssignmentList":{"additionalProperties":false,"properties":{"assignments":{"items":{"$ref":"#/components/schemas/AssignmentInterval"},"type":"array"},"ticket_id":{"format":"uuid","type":"string"}},"required":["assignments","ticket_id"],"type":"object"},"AuditEvent":{"oneOf":[{"$ref":"#/components/schemas/TicketCreatedAuditEvent"},{"$ref":"#/components/schemas/CustodyTransferredAuditEvent"},{"$ref":"#/components/schemas/TicketCommentAddedAuditEvent"},{"$ref":"#/components/schemas/WorkChangedAuditEvent"},{"$ref":"#/components/schemas/WorkflowChangedAuditEvent"},{"$ref":"#/components/schemas/ProofChangedAuditEvent"}]},"AuditPage":{"additionalProperties":false,"properties":{"events":{"items":{"$ref":"#/components/schemas/AuditEvent"},"type":"array"},"next_cursor":{"minimum":1,"type":["integer","null"]},"ticket_id":{"format":"uuid","type":"string"}},"required":["events","next_cursor","ticket_id"],"type":"object"},"BlockIntent":{"additionalProperties":false,"properties":{"affected_stage":{"pattern":"^[a-z][a-z0-9._-]*$","type":["string","null"]},"blocker_id":{"format":"uuid","type":"string"},"blocker_kind":{"enum":["dependency","operator_action","policy","resource","technical"],"type":"string"},"board_impact":{"type":"boolean"},"dependency_ref":{"maxLength":256,"type":["string","null"]},"expected_version":{"minimum":1,"type":"integer"},"kind":{"const":"block"},"next_check_at":{"format":"date-time","type":["string","null"]},"owner_principal_id":{"format":"uuid","type":"string"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"reason_class":{"maxLength":64,"minLength":1,"type":"string"},"resolution_condition":{"maxLength":500,"minLength":1,"type":"string"},"source_ref":{"maxLength":256,"minLength":1,"type":"string"}},"required":["kind","expected_version","reason","blocker_id","blocker_kind","reason_class","owner_principal_id","source_ref","affected_stage","resolution_condition","next_check_at","dependency_ref","board_impact"],"type":"object"},"BlockerOpenedAuditData":{"additionalProperties":false,"properties":{"blocker_id":{"format":"uuid","type":"string"},"board_impact":{"type":"boolean"},"reason":{"maxLength":500,"minLength":1,"type":"string"}},"required":["blocker_id","board_impact","reason"],"type":"object"},"BlockerResolvedAuditData":{"additionalProperties":false,"properties":{"blocker_id":{"format":"uuid","type":"string"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"resolution_evidence_ref":{"maxLength":256,"minLength":1,"type":"string"}},"required":["blocker_id","reason","resolution_evidence_ref"],"type":"object"},"BoardCard":{"additionalProperties":false,"properties":{"activity_class":{"enum":["work","verification",null],"type":["string","null"]},"assignee_id":{"format":"uuid","type":["string","null"]},"blocker_opened_at":{"format":"date-time","type":["string","null"]},"blocker_reason":{"type":["string","null"]},"custodian_id":{"format":"uuid","type":"string"},"delivery_facts":{"items":{"type":"string"},"type":"array"},"lane":{"$ref":"#/components/schemas/BoardLane"},"priority":{"$ref":"#/components/schemas/Priority"},"risk":{"type":["string","null"]},"stage_key":{"pattern":"^[a-z][a-z0-9._-]*$","type":["string","null"]},"stage_label":{"type":["string","null"]},"ticket_id":{"format":"uuid","type":"string"},"title":{"type":"string"},"underlying_lane":{"enum":["backlog","ready","in_progress","in_review","complete",null],"type":["string","null"]},"version":{"minimum":1,"type":"integer"}},"required":["activity_class","assignee_id","blocker_opened_at","blocker_reason","custodian_id","delivery_facts","lane","priority","risk","stage_key","stage_label","ticket_id","title","underlying_lane","version"],"type":"object"},"BoardLane":{"enum":["backlog","ready","in_progress","in_review","blocked","complete"],"type":"string"},"BoardView":{"additionalProperties":false,"properties":{"cards":{"items":{"$ref":"#/components/schemas/BoardCard"},"type":"array"},"health":{"$ref":"#/components/schemas/ProjectionHealth"},"projection_watermark":{"minimum":0,"type":"integer"},"source_watermark":{"minimum":0,"type":"integer"}},"required":["cards","health","projection_watermark","source_watermark"],"type":"object"},"BootstrapReceipt":{"additionalProperties":false,"properties":{"command_id":{"format":"uuid","type":"string"},"commander_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"operator_id":{"format":"uuid","type":"string"},"receipt_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"tenant_id":{"format":"uuid","type":"string"}},"required":["command_id","commander_id","durability_state","event_ids","operator_id","receipt_digest","tenant_id"],"type":"object"},"BootstrapRequest":{"additionalProperties":false,"properties":{"commander_name":{"maxLength":120,"minLength":1,"type":"string"},"commander_vault_ref":{"pattern":"^vault-ref:[a-z0-9/_-]+$","type":"string"},"operator_credential_ref":{"pattern":"^credential-ref:[a-z0-9/_-]+$","type":"string"},"operator_name":{"maxLength":120,"minLength":1,"type":"string"},"operator_vault_ref":{"pattern":"^vault-ref:[a-z0-9/_-]+$","type":"string"},"tenant_name":{"maxLength":120,"minLength":1,"type":"string"},"tenant_slug":{"pattern":"^[a-z][a-z0-9-]{1,62}$","type":"string"}},"required":["commander_name","commander_vault_ref","operator_credential_ref","operator_name","operator_vault_ref","tenant_name","tenant_slug"],"type":"object"},"BundleAction":{"additionalProperties":false,"properties":{"component":{"$ref":"#/components/schemas/ComponentReference"},"kind":{"$ref":"#/components/schemas/BundleActionKind"}},"required":["component","kind"],"type":"object"},"BundleActionKind":{"enum":["create","reuse_exact","supersede","deprecate","assignment_change","pointer_change","no_op"],"type":"string"},"BundleCheck":{"additionalProperties":false,"properties":{"code":{"pattern":"^[a-z][a-z0-9._-]{1,95}$","type":"string"},"status":{"enum":["passed","warning"],"type":"string"}},"required":["code","status"],"type":"object"},"CompanyBundleApplyRequest":{"additionalProperties":false,"properties":{"bundle":{"$ref":"#/components/schemas/CompanyBundleDocument"},"expected_active_version":{"minimum":0,"type":"integer"},"plan_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"}},"required":["bundle","expected_active_version","plan_digest"],"type":"object"},"CompanyBundleAssignment":{"additionalProperties":false,"properties":{"component":{"$ref":"#/components/schemas/ComponentReference"},"slot":{"pattern":"^[a-z][a-z0-9._-]{1,63}$","type":"string"},"subject":{"pattern":"^[a-z][a-z0-9._-]*:[a-z][a-z0-9._-]*$","type":"string"}},"required":["component","slot","subject"],"type":"object"},"CompanyBundleCommandResult":{"additionalProperties":false,"properties":{"active_version":{"minimum":1,"type":"integer"},"bundle_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"plan_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"}},"required":["active_version","bundle_digest","command_id","durability_state","event_ids","plan_digest"],"type":"object"},"CompanyBundleDocument":{"additionalProperties":false,"properties":{"assignments":{"items":{"$ref":"#/components/schemas/CompanyBundleAssignment"},"maxItems":512,"type":"array"},"company":{"$ref":"#/components/schemas/CompanyIdentity"},"resources":{"items":{"$ref":"#/components/schemas/CompanyBundleResource"},"maxItems":512,"minItems":1,"type":"array"},"schema":{"const":"ctower.company-bundle/v1"},"secret_binding_refs":{"items":{"$ref":"#/components/schemas/SecretBindingReference"},"maxItems":128,"type":"array"}},"required":["assignments","company","resources","schema","secret_binding_refs"],"type":"object"},"CompanyBundleExportMetadata":{"additionalProperties":false,"properties":{"activated_at":{"format":"date-time","type":"string"},"actor_principal_id":{"format":"uuid","type":"string"},"checks":{"items":{"$ref":"#/components/schemas/BundleCheck"},"type":"array"},"command_id":{"format":"uuid","type":"string"}},"required":["activated_at","actor_principal_id","checks","command_id"],"type":"object"},"CompanyBundleExportResult":{"additionalProperties":false,"properties":{"active_version":{"minimum":1,"type":"integer"},"bundle":{"$ref":"#/components/schemas/CompanyBundleDocument"},"bundle_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"metadata":{"$ref":"#/components/schemas/CompanyBundleExportMetadata"}},"required":["active_version","bundle","bundle_digest","metadata"],"type":"object"},"CompanyBundlePlan":{"additionalProperties":false,"properties":{"actions":{"items":{"$ref":"#/components/schemas/BundleAction"},"type":"array"},"base_bundle_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"base_version":{"minimum":0,"type":"integer"},"checks":{"items":{"$ref":"#/components/schemas/BundleCheck"},"type":"array"},"plan_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"proposed_bundle_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"warnings":{"items":{"maxLength":500,"type":"string"},"type":"array"}},"required":["actions","base_bundle_digest","base_version","checks","plan_digest","proposed_bundle_digest","warnings"],"type":"object"},"CompanyBundleRequest":{"additionalProperties":false,"properties":{"bundle":{"$ref":"#/components/schemas/CompanyBundleDocument"}},"required":["bundle"],"type":"object"},"CompanyBundleResource":{"additionalProperties":false,"properties":{"component":{"$ref":"#/components/schemas/VersionedComponent"},"payload":{"type":"object"}},"required":["component","payload"],"type":"object"},"CompanyBundleValidationResult":{"additionalProperties":false,"properties":{"bundle_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"checks":{"items":{"$ref":"#/components/schemas/BundleCheck"},"type":"array"},"valid":{"type":"boolean"},"warnings":{"items":{"maxLength":500,"type":"string"},"type":"array"}},"required":["bundle_digest","checks","valid","warnings"],"type":"object"},"CompanyIdentity":{"additionalProperties":false,"properties":{"display_name":{"maxLength":128,"minLength":1,"type":"string"},"key":{"pattern":"^[a-z][a-z0-9-]{2,63}$","type":"string"}},"required":["display_name","key"],"type":"object"},"ComponentCompatibility":{"additionalProperties":false,"properties":{"ctower":{"maxLength":80,"minLength":1,"type":"string"},"requires":{"items":{"$ref":"#/components/schemas/ComponentReference"},"maxItems":128,"type":"array"}},"required":["ctower","requires"],"type":"object"},"ComponentKind":{"enum":["workflow","execution_policy","gate_policy","evidence_policy","goal","project","agent_profile","persona","skill","tool","capability","environment","image","harness","supervisor","target","workspace","telemetry","placement_policy","extension","cadence_policy","notification","integration","adapter","checkpoint"],"type":"string"},"ComponentProvenance":{"additionalProperties":false,"properties":{"digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"kind":{"pattern":"^[a-z][a-z0-9._-]{1,63}$","type":"string"},"source":{"maxLength":512,"minLength":1,"type":"string"}},"required":["digest","kind","source"],"type":"object"},"ComponentReference":{"additionalProperties":false,"properties":{"content_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"key":{"pattern":"^[a-z][a-z0-9.-]{2,127}$","type":"string"},"kind":{"$ref":"#/components/schemas/ComponentKind"},"revision":{"minimum":1,"type":"integer"}},"required":["content_digest","key","kind","revision"],"type":"object"},"ComponentScope":{"additionalProperties":false,"properties":{"project":{"pattern":"^[a-z][a-z0-9.-]{2,127}$","type":["string","null"]},"tenant":{"pattern":"^[a-z][a-z0-9-]{2,63}$","type":"string"}},"required":["project","tenant"],"type":"object"},"ControlHealth":{"additionalProperties":false,"properties":{"availability":{"$ref":"#/components/schemas/HealthDimension"},"completeness":{"$ref":"#/components/schemas/HealthDimension"},"integrity":{"$ref":"#/components/schemas/HealthDimension"},"observed_at":{"format":"date-time","type":"string"},"schema_id":{"const":"ctower.health/v1"},"status":{"$ref":"#/components/schemas/HealthStatus"}},"required":["schema_id","status","observed_at","availability","completeness","integrity"],"type":"object"},"CtowerProjectAliasPlanBindRequest":{"additionalProperties":false,"properties":{"alias_map_artifact":{"maxLength":4194304,"minLength":2,"type":"string"},"alias_map_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"attention_required":{"const":0},"cutover_id":{"format":"uuid","type":"string"},"export_equality_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"fence_observer_credential_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"fence_observer_expires_at":{"format":"date-time","type":"string"},"fence_registry_artifact":{"maxLength":2097152,"minLength":2,"type":"string"},"import_plan_artifact":{"maxLength":8388608,"minLength":2,"type":"string"},"reviewer_key_ref":{"pattern":"^signing-key-ref:[a-z0-9/_-]{3,255}$","type":"string"},"reviewer_key_version":{"minimum":1,"type":"integer"},"reviewer_public_key_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"run_id":{"format":"uuid","type":"string"}},"required":["run_id","cutover_id","export_equality_digest","alias_map_digest","reviewer_key_ref","reviewer_key_version","reviewer_public_key_digest","attention_required","alias_map_artifact","import_plan_artifact","fence_registry_artifact","fence_observer_credential_digest","fence_observer_expires_at"],"type":"object"},"CtowerProjectCutoverHealth":{"additionalProperties":false,"properties":{"authority_mode":{"enum":["legacy_writable","development_single_writer","disaster_safe"],"type":"string"},"banner":{"minLength":1,"type":"string"},"cutover_id":{"format":"uuid","type":["string","null"]},"data_class":{"enum":["RECONSTRUCTIBLE_ONLY","DISASTER_SAFE_CTOWER_ENGINEERING"],"type":"string"},"durability_claim":{"enum":["CP3_D_NOT_PROVEN","CP3_D_PROVEN"],"type":"string"},"import_run_id":{"format":"uuid","type":["string","null"]},"legacy_writer_fence":{"enum":["not_armed","enforced","unknown"],"type":"string"},"migration_digests":{"$ref":"#/components/schemas/MigrationHealthDigests"},"phase":{"enum":["not_started","source_selection_frozen","export_equal","alias_plan_bound","import_in_progress","reconciled","prepared","development_epoch_committed","disaster_safe_active"],"type":"string"},"projection_completeness":{"enum":["current","stale","STATE_UNKNOWN"],"type":"string"},"projection_watermark":{"minimum":0,"type":"integer"},"recovery_claim":{"enum":["EXTERNAL_FAILURE_DOMAIN_UNPROVEN","EXTERNAL_FAILURE_DOMAIN_PROVEN"],"type":"string"},"schema":{"const":"ctower.ctower-project-cutover-health/v1"},"source_watermark":{"minimum":0,"type":"integer"},"split_brain":{"enum":["clear","detected","unknown"],"type":"string"},"writes_enabled":{"type":"boolean"}},"required":["schema","cutover_id","authority_mode","phase","writes_enabled","durability_claim","recovery_claim","data_class","legacy_writer_fence","split_brain","projection_completeness","source_watermark","projection_watermark","import_run_id","migration_digests","banner"],"type":"object"},"CtowerProjectEpochRefusalRequest":{"additionalProperties":false,"properties":{"cutover_id":{"format":"uuid","type":"string"},"fence_registry_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"reconciliation_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"run_id":{"format":"uuid","type":"string"}},"required":["cutover_id","run_id","reconciliation_digest","fence_registry_digest"],"type":"object"},"CtowerProjectExactAliasOperation":{"additionalProperties":false,"properties":{"identity":{"$ref":"#/components/schemas/MigrationOperationIdentity"},"operation":{"const":"exact_alias"},"project_key":{"const":"ctower"},"source":{"$ref":"#/components/schemas/MigrationSourceIdentity"},"target_ticket_id":{"format":"uuid","type":"string"}},"required":["operation","identity","project_key","source","target_ticket_id"],"type":"object"},"CtowerProjectExportEqualityBindRequest":{"additionalProperties":false,"properties":{"cutover_id":{"format":"uuid","type":"string"},"equality_report_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"export_a_artifact":{"maxLength":4194304,"minLength":2,"type":"string"},"export_b_artifact":{"maxLength":4194304,"minLength":2,"type":"string"},"export_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"export_equality_artifact":{"maxLength":2097152,"minLength":2,"type":"string"},"inventory_a_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"inventory_b_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"result":{"const":"equal"},"reviewer_key_ref":{"pattern":"^signing-key-ref:[a-z0-9/_-]{3,255}$","type":"string"},"reviewer_key_version":{"minimum":1,"type":"integer"},"reviewer_public_key_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"run_id":{"format":"uuid","type":"string"},"selection_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"}},"required":["run_id","cutover_id","selection_digest","inventory_a_digest","inventory_b_digest","export_digest","equality_report_digest","reviewer_key_ref","reviewer_key_version","reviewer_public_key_digest","result","export_a_artifact","export_b_artifact","export_equality_artifact"],"type":"object"},"CtowerProjectFenceObservationRequest":{"additionalProperties":false,"properties":{"cutover_id":{"format":"uuid","type":"string"},"disables_writes":{"type":"boolean"},"file_identity":{"$ref":"#/components/schemas/MigrationFenceFileIdentity"},"from_offset":{"minimum":0,"type":"integer"},"may_enable_writes":{"const":false},"observation_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"observation_id":{"format":"uuid","type":"string"},"observed_at":{"format":"date-time","type":"string"},"previous_observation_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"project_key":{"const":"ctower"},"reason_code":{"enum":["no_scoped_append","scoped_row_appended","truncated_row","inode_replaced","file_truncated","unreadable_gap","classifier_unknown","monitor_interval_missing","registry_mismatch","observation_stale","observation_from_future","offset_reversed","pointer_mismatch"],"type":"string"},"registry_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"registry_id":{"format":"uuid","type":"string"},"registry_revision":{"minimum":1,"type":"integer"},"run_id":{"format":"uuid","type":"string"},"schema":{"const":"ctower.ctower-project-fence-observation/v2"},"sequence":{"minimum":1,"type":"integer"},"source_pointer_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"status":{"enum":["clear","detected","unknown"],"type":"string"},"tenant_key":{"const":"ctower"},"to_offset":{"minimum":0,"type":"integer"}},"required":["schema","observation_id","run_id","cutover_id","tenant_key","project_key","registry_id","registry_revision","registry_digest","source_pointer_digest","sequence","previous_observation_digest","observed_at","from_offset","to_offset","file_identity","status","reason_code","observation_digest","disables_writes","may_enable_writes"],"type":"object"},"CtowerProjectImportBatchRequest":{"additionalProperties":false,"properties":{"batch_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"batch_index":{"minimum":0,"type":"integer"},"cutover_id":{"format":"uuid","type":"string"},"operations":{"items":{"$ref":"#/components/schemas/CtowerProjectImportOperation"},"maxItems":64,"minItems":1,"type":"array"},"run_id":{"format":"uuid","type":"string"},"schema":{"const":"ctower.ctower-project-import-batch/v1"}},"required":["schema","run_id","cutover_id","batch_index","batch_digest","operations"],"type":"object"},"CtowerProjectImportBatchResult":{"additionalProperties":false,"properties":{"accepted_position":{"minimum":1,"type":["integer","null"]},"batch_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"batch_index":{"minimum":0,"type":"integer"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"projection_watermark":{"minimum":0,"type":"integer"},"record_watermark":{"minimum":1,"type":"integer"},"results":{"items":{"$ref":"#/components/schemas/MigrationImportOperationResult"},"maxItems":64,"minItems":1,"type":"array"},"run_id":{"format":"uuid","type":"string"}},"required":["run_id","batch_index","batch_digest","results","record_watermark","projection_watermark","durability_state","accepted_position"],"type":"object"},"CtowerProjectImportCorrectionRequest":{"additionalProperties":false,"properties":{"correction_id":{"format":"uuid","type":"string"},"correction_kind":{"enum":["alias","source_link","relation"],"type":"string"},"cutover_id":{"format":"uuid","type":"string"},"expected_current_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"project_key":{"const":"ctower"},"reason":{"maxLength":1000,"minLength":1,"type":"string"},"replacement":{"$ref":"#/components/schemas/MigrationCorrectionReplacement"},"reviewer_id":{"format":"uuid","type":"string"},"run_id":{"format":"uuid","type":"string"},"schema":{"const":"ctower.ctower-project-import-correction/v1"},"superseded_revision":{"$ref":"#/components/schemas/MigrationCorrectionRevision"},"tenant_key":{"const":"ctower"}},"required":["schema","correction_id","run_id","cutover_id","tenant_key","project_key","correction_kind","superseded_revision","expected_current_digest","replacement","reason","reviewer_id"],"type":"object"},"CtowerProjectImportFinalizeRequest":{"additionalProperties":false,"properties":{"cutover_id":{"format":"uuid","type":"string"},"expected_run_semantic_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"reconciliation_artifact":{"maxLength":16777216,"minLength":2,"type":"string"},"run_id":{"format":"uuid","type":"string"}},"required":["run_id","cutover_id","expected_run_semantic_digest","reconciliation_artifact"],"type":"object"},"CtowerProjectImportOperation":{"oneOf":[{"$ref":"#/components/schemas/CtowerProjectTicketSeedOperation"},{"$ref":"#/components/schemas/CtowerProjectExactAliasOperation"},{"$ref":"#/components/schemas/CtowerProjectTicketRelationOperation"},{"$ref":"#/components/schemas/CtowerProjectSourceLinkOperation"}]},"CtowerProjectImportRun":{"additionalProperties":false,"properties":{"accepted_position":{"minimum":1,"type":["integer","null"]},"conservation":{"oneOf":[{"$ref":"#/components/schemas/MigrationConservation"},{"type":"null"}]},"counts":{"$ref":"#/components/schemas/MigrationImportCounts"},"cutover_id":{"format":"uuid","type":"string"},"dispositions":{"oneOf":[{"$ref":"#/components/schemas/MigrationDispositions"},{"type":"null"}]},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"export_native_watermark":{"minimum":0,"type":"integer"},"importer_binding":{"$ref":"#/components/schemas/MigrationImporterBinding"},"pass_two_measurement":{"oneOf":[{"$ref":"#/components/schemas/MigrationPassTwoMeasurement"},{"type":"null"}]},"pinned_digests":{"$ref":"#/components/schemas/MigrationPinnedDigests"},"project_key":{"const":"ctower"},"projection_watermark":{"minimum":0,"type":"integer"},"reconciliation_graph":{"oneOf":[{"$ref":"#/components/schemas/MigrationReconciliationGraph"},{"type":"null"}]},"record_watermark":{"minimum":0,"type":"integer"},"refusals":{"items":{"$ref":"#/components/schemas/MigrationRefusal"},"type":"array"},"reviewer_key":{"$ref":"#/components/schemas/MigrationReviewerKey"},"run_id":{"format":"uuid","type":"string"},"schema":{"const":"ctower.ctower-project-import-run/v2"},"semantic_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"source_native_watermark":{"minimum":0,"type":"integer"},"state":{"enum":["created","export_equality_bound","alias_plan_bound","importing","pass_one_complete","pass_two_started","pass_two_noop","reconciled"],"type":"string"},"tenant_key":{"const":"ctower"}},"required":["schema","run_id","cutover_id","tenant_key","project_key","state","pinned_digests","reviewer_key","importer_binding","counts","dispositions","conservation","reconciliation_graph","pass_two_measurement","source_native_watermark","export_native_watermark","record_watermark","projection_watermark","refusals","semantic_digest","durability_state","accepted_position"],"type":"object"},"CtowerProjectImportRunCreateRequest":{"additionalProperties":false,"properties":{"build_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"client_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"cutover_id":{"format":"uuid","type":"string"},"importer_credential_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"importer_expires_at":{"format":"date-time","type":"string"},"operation_registry_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"project_key":{"const":"ctower"},"reviewer_key_ref":{"pattern":"^signing-key-ref:[a-z0-9/_-]{3,255}$","type":"string"},"reviewer_key_version":{"minimum":1,"type":"integer"},"reviewer_public_key_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"schema_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"source_selection_artifact":{"maxLength":2097152,"minLength":2,"type":"string"},"source_selection_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"tenant_key":{"const":"ctower"}},"required":["cutover_id","tenant_key","project_key","source_selection_digest","source_selection_artifact","build_digest","client_digest","schema_digest","operation_registry_digest","reviewer_key_ref","reviewer_key_version","reviewer_public_key_digest","importer_credential_digest","importer_expires_at"],"type":"object"},"CtowerProjectMigrationReceipt":{"additionalProperties":false,"properties":{"accepted_position":{"minimum":1,"type":["integer","null"]},"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"object_id":{"format":"uuid","type":"string"},"record_position":{"minimum":1,"type":"integer"},"revision":{"minimum":1,"type":"integer"},"semantic_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"}},"required":["object_id","revision","command_id","event_ids","record_position","semantic_digest","durability_state","accepted_position"],"type":"object"},"CtowerProjectReconciliationResult":{"additionalProperties":false,"properties":{"accepted_position":{"minimum":1,"type":["integer","null"]},"actual_graph":{"$ref":"#/components/schemas/MigrationReconciliationGraph"},"cutover_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"expected_graph":{"$ref":"#/components/schemas/MigrationReconciliationGraph"},"pass_two_measurement":{"$ref":"#/components/schemas/MigrationPassTwoMeasurement"},"pinned_digests":{"$ref":"#/components/schemas/MigrationPinnedDigests"},"project_key":{"const":"ctower"},"reconciled_at":{"format":"date-time","type":"string"},"reconciliation_id":{"format":"uuid","type":"string"},"report_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"review":{"$ref":"#/components/schemas/MigrationReview"},"reviewer_key":{"$ref":"#/components/schemas/MigrationReviewerKey"},"run_id":{"format":"uuid","type":"string"},"schema":{"const":"ctower.ctower-project-reconciliation/v2"},"signature":{"$ref":"#/components/schemas/MigrationDetachedSignature"},"target_semantic_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"watermarks":{"$ref":"#/components/schemas/MigrationWatermarks"}},"required":["schema","reconciliation_id","run_id","cutover_id","project_key","pinned_digests","reviewer_key","expected_graph","actual_graph","pass_two_measurement","watermarks","target_semantic_digest","reconciled_at","review","report_digest","signature","durability_state","accepted_position"],"type":"object"},"CtowerProjectSourceLinkOperation":{"additionalProperties":false,"properties":{"identity":{"$ref":"#/components/schemas/MigrationOperationIdentity"},"link_class":{"enum":["decision","external_effect","artifact_not_proof","provenance"],"type":"string"},"linked_not_proof":{"const":true},"operation":{"const":"source_link"},"project_key":{"const":"ctower"},"reason_code":{"pattern":"^[a-z][a-z0-9._-]{2,95}$","type":"string"},"source":{"$ref":"#/components/schemas/MigrationSourceIdentity"},"target_id":{"maxLength":256,"minLength":1,"type":"string"},"target_kind":{"enum":["ticket","ticket_relation","checkpoint","decision","artifact","external_effect"],"type":"string"}},"required":["operation","identity","project_key","source","link_class","target_kind","target_id","reason_code","linked_not_proof"],"type":"object"},"CtowerProjectTicketRelationOperation":{"additionalProperties":false,"properties":{"identity":{"$ref":"#/components/schemas/MigrationOperationIdentity"},"operation":{"const":"ticket_relation"},"project_key":{"const":"ctower"},"reason":{"maxLength":500,"minLength":1,"pattern":"^[^\\u0000-\\u001F\\u007F]+$","type":"string"},"relation_id":{"format":"uuid","type":"string"},"relation_kind":{"enum":["parent_of","depends_on","blocks","duplicates","relates_to","caused_by"],"type":"string"},"source_ticket_id":{"format":"uuid","type":"string"},"target_ticket_id":{"format":"uuid","type":"string"}},"required":["operation","identity","project_key","relation_id","relation_kind","source_ticket_id","target_ticket_id","reason"],"type":"object"},"CtowerProjectTicketSeedOperation":{"additionalProperties":false,"properties":{"identity":{"$ref":"#/components/schemas/MigrationOperationIdentity"},"initial_commander_custodian_id":{"format":"uuid","type":"string"},"operation":{"const":"ticket_seed"},"priority":{"const":"P2"},"project_key":{"const":"ctower"},"source":{"$ref":"#/components/schemas/MigrationSourceIdentity"},"title":{"maxLength":200,"minLength":1,"pattern":"^[^\\u0000-\\u001F\\u007F]+$","type":"string"}},"required":["operation","identity","project_key","priority","title","source","initial_commander_custodian_id"],"type":"object"},"CustodyTransferRequest":{"additionalProperties":false,"properties":{"expected_version":{"minimum":1,"type":"integer"},"from_custodian_id":{"format":"uuid","type":"string"},"protected_transfer":{"type":"boolean"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"to_custodian_id":{"format":"uuid","type":"string"}},"required":["expected_version","from_custodian_id","protected_transfer","reason","to_custodian_id"],"type":"object"},"CustodyTransferredAuditEvent":{"additionalProperties":false,"properties":{"actor_principal_id":{"format":"uuid","type":"string"},"command_id":{"format":"uuid","type":"string"},"event_hash":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"event_id":{"format":"uuid","type":"string"},"kind":{"const":"ticket.custody_transferred"},"occurred_at":{"format":"date-time","type":"string"},"payload":{"$ref":"#/components/schemas/CustodyTransferredPayload"},"record_position":{"minimum":1,"type":"integer"},"sequence":{"minimum":1,"type":"integer"},"stream_id":{"pattern":"^ticket:[0-9a-f-]{36}$","type":"string"}},"required":["actor_principal_id","command_id","event_hash","event_id","kind","occurred_at","payload","record_position","sequence","stream_id"],"type":"object"},"CustodyTransferredPayload":{"additionalProperties":false,"properties":{"from_custodian_id":{"format":"uuid","type":"string"},"reason":{"type":"string"},"to_custodian_id":{"format":"uuid","type":"string"}},"required":["from_custodian_id","reason","to_custodian_id"],"type":"object"},"DeferIntent":{"additionalProperties":false,"properties":{"expected_version":{"minimum":1,"type":"integer"},"kind":{"const":"defer"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"review_after":{"format":"date-time","type":"string"}},"required":["kind","expected_version","reason","review_after"],"type":"object"},"DeferredAuditData":{"additionalProperties":false,"properties":{"episode_number":{"minimum":1,"type":"integer"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"review_after":{"format":"date-time","type":"string"}},"required":["episode_number","reason","review_after"],"type":"object"},"DurabilityState":{"enum":["durability_pending","accepted"],"type":"string"},"EvidenceRequest":{"additionalProperties":false,"properties":{"artifact_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"candidate_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"content":{"maxLength":100000,"minLength":1,"type":"string"},"criterion_key":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"},"evidence_id":{"format":"uuid","type":"string"},"expected_version":{"minimum":1,"type":"integer"}},"required":["expected_version","evidence_id","criterion_key","candidate_digest","artifact_digest","content"],"type":"object"},"FreezeCriteriaRequest":{"additionalProperties":false,"properties":{"candidate_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"criteria":{"items":{"$ref":"#/components/schemas/ProofCriterion"},"minItems":1,"type":"array"},"expected_version":{"minimum":0,"type":"integer"}},"required":["expected_version","candidate_digest","criteria"],"type":"object"},"HealthContributor":{"additionalProperties":false,"properties":{"key":{"$ref":"#/components/schemas/HealthContributorKey"},"observed_at":{"format":"date-time","type":"string"},"owner":{"maxLength":128,"minLength":1,"type":"string"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"status":{"$ref":"#/components/schemas/HealthStatus"},"threshold_seconds":{"minimum":0,"type":"integer"},"watermark":{"minimum":0,"type":["integer","null"]}},"required":["key","status","watermark","threshold_seconds","observed_at","owner","reason"],"type":"object"},"HealthContributorKey":{"enum":["durability","scheduler","outbox","projection","backup","anchor","object","synthetic"],"type":"string"},"HealthDimension":{"additionalProperties":false,"properties":{"contributors":{"items":{"$ref":"#/components/schemas/HealthContributor"},"minItems":1,"type":"array"},"status":{"$ref":"#/components/schemas/HealthStatus"}},"required":["status","contributors"],"type":"object"},"HealthStatus":{"enum":["HEALTHY","DEGRADED","STATE_UNKNOWN"],"type":"string"},"IntakeCommandResult":{"additionalProperties":false,"properties":{"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"maxItems":2,"minItems":1,"type":"array"},"inbound_event_id":{"format":"uuid","type":"string"},"outcome":{"$ref":"#/components/schemas/IntakeOutcome"},"project_key":{"pattern":"^[a-z][a-z0-9-]{2,63}$","type":"string"},"quarantine_reason":{"maxLength":500,"type":["string","null"]},"source":{"$ref":"#/components/schemas/SourceReference"},"thread_id":{"format":"uuid","type":"string"},"thread_version":{"minimum":1,"type":"integer"},"ticket_id":{"format":"uuid","type":["string","null"]},"ticket_version":{"minimum":1,"type":["integer","null"]}},"required":["command_id","durability_state","event_ids","inbound_event_id","outcome","project_key","quarantine_reason","source","thread_id","thread_version","ticket_id","ticket_version"],"type":"object"},"IntakeIntent":{"enum":["discussion","create_ticket","link_ticket"],"type":"string"},"IntakeOutcome":{"enum":["discussion","ticket_created","ticket_linked","quarantined"],"type":"string"},"IntakePromotionIntent":{"enum":["create_ticket","link_ticket"],"type":"string"},"IntakePromotionRequest":{"additionalProperties":false,"properties":{"expected_thread_version":{"minimum":1,"type":"integer"},"expected_ticket_version":{"minimum":1,"type":["integer","null"]},"initial_custodian_id":{"format":"uuid","type":["string","null"]},"intent":{"$ref":"#/components/schemas/IntakePromotionIntent"},"priority":{"oneOf":[{"$ref":"#/components/schemas/Priority"},{"type":"null"}]},"target_ticket_id":{"format":"uuid","type":["string","null"]},"title":{"maxLength":200,"minLength":1,"type":["string","null"]}},"required":["expected_thread_version","intent"],"type":"object"},"IntakeSubmitRequest":{"additionalProperties":false,"properties":{"content":{"maxLength":65536,"minLength":1,"type":"string"},"expected_thread_version":{"minimum":1,"type":["integer","null"]},"expected_ticket_version":{"minimum":1,"type":["integer","null"]},"initial_custodian_id":{"format":"uuid","type":["string","null"]},"intent":{"$ref":"#/components/schemas/IntakeIntent","default":"discussion"},"priority":{"oneOf":[{"$ref":"#/components/schemas/Priority"},{"type":"null"}]},"project_key":{"pattern":"^[a-z][a-z0-9-]{2,63}$","type":"string"},"source":{"$ref":"#/components/schemas/SourceReference"},"taint":{"$ref":"#/components/schemas/IntakeTaint","default":"authenticated"},"target_ticket_id":{"format":"uuid","type":["string","null"]},"thread_id":{"format":"uuid","type":["string","null"]},"title":{"maxLength":200,"minLength":1,"type":["string","null"]}},"required":["content","project_key","source"],"type":"object"},"IntakeTaint":{"enum":["authenticated","external_untrusted","quarantine_required"],"type":"string"},"MigrationAliasCorrection":{"additionalProperties":false,"properties":{"disposition":{"enum":["alias_linked_existing","exact_duplicate","provenance_only"],"type":"string"},"kind":{"const":"alias"},"target_ticket_id":{"format":"uuid","type":"string"}},"required":["kind","target_ticket_id","disposition"],"type":"object"},"MigrationConservation":{"additionalProperties":false,"properties":{"alias_forks_or_cycles":{"const":0},"checkpoint_definitions":{"const":14},"forbidden_data_items":{"const":0},"forbidden_relation_cycles":{"const":0},"missing_relation_endpoints":{"const":0},"pass_two_new_domain_facts":{"const":0},"pass_two_new_events":{"const":0},"pass_two_new_outbox_rows":{"const":0},"pass_two_projection_semantic_delta":{"const":0},"pass_two_record_position_delta":{"const":0},"selected_logical_items":{"minimum":1,"type":"integer"},"selected_request_logical":{"const":86},"selected_request_physical_snapshots":{"const":243},"stable_aliases":{"const":27},"unexpected_sources":{"const":0},"unresolved_active_claims":{"const":0},"unresolved_aliases":{"const":0}},"required":["selected_logical_items","selected_request_logical","selected_request_physical_snapshots","stable_aliases","checkpoint_definitions","unresolved_aliases","alias_forks_or_cycles","missing_relation_endpoints","forbidden_relation_cycles","unresolved_active_claims","unexpected_sources","forbidden_data_items","pass_two_new_domain_facts","pass_two_new_events","pass_two_new_outbox_rows","pass_two_record_position_delta","pass_two_projection_semantic_delta"],"type":"object"},"MigrationCorrectionReplacement":{"oneOf":[{"$ref":"#/components/schemas/MigrationAliasCorrection"},{"$ref":"#/components/schemas/MigrationSourceLinkCorrection"},{"$ref":"#/components/schemas/MigrationRelationCorrection"}]},"MigrationCorrectionRevision":{"additionalProperties":false,"properties":{"object_id":{"format":"uuid","type":"string"},"revision":{"minimum":1,"type":"integer"}},"required":["object_id","revision"],"type":"object"},"MigrationDetachedSignature":{"additionalProperties":false,"properties":{"algorithm":{"const":"Ed25519"},"key_ref":{"pattern":"^signing-key-ref:[a-z0-9/_-]{3,255}$","type":"string"},"key_version":{"minimum":1,"type":"integer"},"public_key_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"signature":{"pattern":"^[A-Za-z0-9_-]{86}$","type":"string"},"signed_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"}},"required":["algorithm","signed_digest","key_ref","key_version","public_key_digest","signature"],"type":"object"},"MigrationDispositions":{"additionalProperties":false,"properties":{"alias_linked_existing":{"minimum":0,"type":"integer"},"artifact_linked_not_proof":{"minimum":0,"type":"integer"},"attention_required":{"const":0},"created_ticket":{"minimum":0,"type":"integer"},"decision_link":{"minimum":0,"type":"integer"},"exact_duplicate":{"minimum":0,"type":"integer"},"excluded_out_of_scope":{"minimum":0,"type":"integer"},"external_effect_link":{"minimum":0,"type":"integer"},"project_checkpoint_definition":{"minimum":0,"type":"integer"},"provenance_only":{"minimum":0,"type":"integer"}},"required":["created_ticket","alias_linked_existing","project_checkpoint_definition","decision_link","external_effect_link","artifact_linked_not_proof","provenance_only","exact_duplicate","excluded_out_of_scope","attention_required"],"type":"object"},"MigrationFenceFileIdentity":{"additionalProperties":false,"properties":{"device":{"minimum":0,"type":"integer"},"inode":{"minimum":1,"type":"integer"},"scoped_rows_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"}},"required":["device","inode","scoped_rows_digest"],"type":"object"},"MigrationHealthDigests":{"additionalProperties":false,"properties":{"alias_map":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"export_equality":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"fence_observation":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"fence_registry":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"reconciliation":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"source_selection":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]}},"required":["source_selection","export_equality","alias_map","reconciliation","fence_registry","fence_observation"],"type":"object"},"MigrationImportCounts":{"additionalProperties":false,"properties":{"applied_operations":{"minimum":0,"type":"integer"},"planned_operations":{"minimum":0,"type":"integer"},"refused_operations":{"minimum":0,"type":"integer"},"replayed_operations":{"minimum":0,"type":"integer"}},"required":["planned_operations","applied_operations","replayed_operations","refused_operations"],"type":"object"},"MigrationImportOperationResult":{"additionalProperties":false,"properties":{"command_id":{"format":"uuid","type":"string"},"event_ids":{"items":{"format":"uuid","type":"string"},"type":"array"},"occurred_at":{"format":"date-time","type":"string"},"operation_kind":{"enum":["ticket_seed","exact_alias","ticket_relation","source_link"],"type":"string"},"record_position":{"minimum":1,"type":"integer"},"replayed":{"type":"boolean"},"target_id":{"maxLength":256,"minLength":1,"type":"string"}},"required":["command_id","operation_kind","replayed","target_id","event_ids","record_position","occurred_at"],"type":"object"},"MigrationImporterBinding":{"additionalProperties":false,"properties":{"credential_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"expires_at":{"format":"date-time","type":"string"},"principal_kind":{"const":"migration_importer"},"revoked":{"type":"boolean"}},"required":["principal_kind","credential_digest","expires_at","revoked"],"type":"object"},"MigrationOperationIdentity":{"additionalProperties":false,"properties":{"command_id":{"format":"uuid","type":"string"},"immutable_source_id":{"maxLength":512,"minLength":1,"type":"string"},"namespace":{"maxLength":128,"minLength":1,"type":"string"},"operation_kind":{"enum":["ticket_seed","exact_alias","ticket_relation","source_link"],"type":"string"},"planned_target_ref":{"maxLength":256,"minLength":1,"type":"string"},"source_version_or_digest":{"maxLength":256,"minLength":1,"type":"string"}},"required":["namespace","immutable_source_id","source_version_or_digest","operation_kind","planned_target_ref","command_id"],"type":"object"},"MigrationPassTwoMeasurement":{"additionalProperties":false,"properties":{"end_domain_facts":{"minimum":0,"type":"integer"},"end_events":{"minimum":0,"type":"integer"},"end_outbox_rows":{"minimum":0,"type":"integer"},"end_project_delivery_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"end_record_position":{"minimum":0,"type":"integer"},"end_snapshot_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"new_domain_facts":{"const":0},"new_events":{"const":0},"new_outbox_rows":{"const":0},"projection_semantic_delta":{"const":0},"record_position_delta":{"const":0},"start_domain_facts":{"minimum":0,"type":"integer"},"start_events":{"minimum":0,"type":"integer"},"start_outbox_rows":{"minimum":0,"type":"integer"},"start_project_delivery_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"start_record_position":{"minimum":0,"type":"integer"},"start_snapshot_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"}},"required":["start_snapshot_digest","end_snapshot_digest","start_domain_facts","end_domain_facts","new_domain_facts","start_events","end_events","new_events","start_outbox_rows","end_outbox_rows","new_outbox_rows","start_record_position","end_record_position","record_position_delta","start_project_delivery_digest","end_project_delivery_digest","projection_semantic_delta"],"type":"object"},"MigrationPinnedDigests":{"additionalProperties":false,"properties":{"alias_map":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"build":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"client":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"export_equality":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"fence_registry":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"import_plan":{"pattern":"^sha256:[0-9a-f]{64}$","type":["string","null"]},"operation_registry":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"reviewer_public_key":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"schema":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"source_selection":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"}},"required":["source_selection","export_equality","alias_map","import_plan","fence_registry","build","client","schema","operation_registry","reviewer_public_key"],"type":"object"},"MigrationReconciliationGraph":{"additionalProperties":false,"properties":{"active_claims":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"alias_revisions":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"checkpoint_criteria":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"checkpoint_definitions":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"maxItems":14,"minItems":14,"type":"array","uniqueItems":true},"custody_intervals":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"cycles":{"items":{"type":"string"},"maxItems":0,"type":"array"},"events":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"forbidden":{"items":{"type":"string"},"maxItems":0,"type":"array"},"graph_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"lifecycle_facts":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"operation_identities":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"operation_results":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"outbox_rows":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"priority_facts":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"project_delivery_rows":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"maxItems":14,"minItems":14,"type":"array","uniqueItems":true},"relation_endpoints":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"relations":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"source_links":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"stable_aliases":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"tickets":{"items":{"maxLength":8192,"minLength":1,"type":"string"},"type":"array","uniqueItems":true},"unexpected":{"items":{"type":"string"},"maxItems":0,"type":"array"},"unresolved":{"items":{"type":"string"},"maxItems":0,"type":"array"}},"required":["stable_aliases","operation_identities","operation_results","tickets","lifecycle_facts","priority_facts","custody_intervals","active_claims","alias_revisions","relations","relation_endpoints","source_links","checkpoint_definitions","checkpoint_criteria","project_delivery_rows","events","outbox_rows","unexpected","forbidden","unresolved","cycles","graph_digest"],"type":"object"},"MigrationRefusal":{"additionalProperties":false,"properties":{"code":{"pattern":"^[A-Z][A-Z0-9_]{2,95}$","type":"string"},"operation_identity":{"maxLength":512,"minLength":1,"type":"string"}},"required":["code","operation_identity"],"type":"object"},"MigrationRelationCorrection":{"additionalProperties":false,"properties":{"kind":{"const":"relation"},"replacement_relation_id":{"format":"uuid","type":["string","null"]},"superseded_relation_active":{"const":false}},"required":["kind","superseded_relation_active","replacement_relation_id"],"type":"object"},"MigrationReview":{"additionalProperties":false,"properties":{"decision":{"const":"approved"},"reviewed_at":{"format":"date-time","type":"string"},"reviewer_principal_id":{"format":"uuid","type":"string"}},"required":["reviewer_principal_id","reviewed_at","decision"],"type":"object"},"MigrationReviewerKey":{"additionalProperties":false,"properties":{"key_version":{"minimum":1,"type":"integer"},"public_key_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"public_key_ref":{"pattern":"^signing-key-ref:[a-z0-9/_-]{3,255}$","type":"string"}},"required":["public_key_ref","key_version","public_key_digest"],"type":"object"},"MigrationSourceIdentity":{"additionalProperties":false,"properties":{"immutable_source_id":{"maxLength":512,"minLength":1,"type":"string"},"namespace":{"maxLength":128,"minLength":1,"type":"string"},"source_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"source_version":{"maxLength":256,"minLength":1,"type":"string"}},"required":["namespace","immutable_source_id","source_version","source_digest"],"type":"object"},"MigrationSourceLinkCorrection":{"additionalProperties":false,"properties":{"disposition":{"enum":["decision_link","external_effect_link","artifact_linked_not_proof","provenance_only","excluded_out_of_scope"],"type":"string"},"kind":{"const":"source_link"},"target_id":{"maxLength":256,"minLength":1,"type":"string"},"target_kind":{"enum":["ticket","ticket_relation","checkpoint","decision","artifact","external_effect"],"type":"string"}},"required":["kind","target_kind","target_id","disposition"],"type":"object"},"MigrationWatermarks":{"additionalProperties":false,"properties":{"export_native":{"minimum":0,"type":"integer"},"projection_position":{"minimum":0,"type":"integer"},"record_position":{"minimum":0,"type":"integer"},"source_native":{"minimum":0,"type":"integer"}},"required":["source_native","export_native","record_position","projection_position"],"type":"object"},"MutableAssignmentKind":{"enum":["current_assignee","stage_owner","reviewer_assignment"],"type":"string"},"PoisonDispositionAction":{"enum":["retry","tombstone"],"type":"string"},"PoisonDispositionReceipt":{"additionalProperties":false,"properties":{"action":{"$ref":"#/components/schemas/PoisonDispositionAction"},"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"outbox_id":{"format":"uuid","type":"string"},"recorded_at":{"format":"date-time","type":"string"}},"required":["command_id","outbox_id","action","durability_state","event_ids","recorded_at"],"type":"object"},"PoisonDispositionRequest":{"additionalProperties":false,"properties":{"action":{"$ref":"#/components/schemas/PoisonDispositionAction"},"consumer_key":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"topic":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"}},"required":["consumer_key","topic","action","reason"],"type":"object"},"Priority":{"enum":["P0","P1","P2"],"type":"string"},"PriorityChangeRequest":{"additionalProperties":false,"properties":{"expected_version":{"minimum":1,"type":"integer"},"priority":{"$ref":"#/components/schemas/Priority"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"urgent_evidence_ref":{"maxLength":256,"minLength":1,"type":["string","null"]}},"required":["expected_version","priority","reason"],"type":"object"},"PriorityChangedAuditData":{"additionalProperties":false,"properties":{"authority":{"enum":["commander","operator"],"type":"string"},"from_priority":{"$ref":"#/components/schemas/Priority"},"policy_ref":{"const":"ctower.priority-authority@1"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"to_priority":{"$ref":"#/components/schemas/Priority"},"urgent_evidence_ref":{"maxLength":256,"minLength":1,"type":["string","null"]}},"required":["authority","from_priority","policy_ref","reason","to_priority","urgent_evidence_ref"],"type":"object"},"Problem":{"additionalProperties":false,"properties":{"code":{"enum":["bootstrap-consumed","bootstrap-expired","bootstrap-nonempty","bootstrap-origin","bundle-base-conflict","bundle-compatibility-refused","bundle-digest-mismatch","bundle-grant-refused","bundle-independence-refused","bundle-no-effect-refused","bundle-not-active","bundle-plan-mismatch","bundle-recovery-unavailable","bundle-reference-invalid","bundle-schema-invalid","bundle-security-refused","durability_pending","i1-7c-required","idempotency-conflict","intake-already-promoted","intake-promotion-ineligible","intake-source-conflict","migration-alias-conflict","migration-capability-denied","migration-correction-conflict","migration-digest-mismatch","migration-export-nondeterminism","migration-fence-detected","migration-import-finalization-refused","migration-operation-drift","migration-relation-invalid","migration-run-conflict","migration-signature-invalid","migration-source-selection-drift","migration-source-tainted","poison-not-found","project-delivery-unavailable","request-body-too-large","proof-candidate-author-mismatch","proof-candidate-digest-invalid","proof-candidate-digest-not-current","proof-candidate-unchanged","proof-criteria-already-frozen","proof-criteria-invalid","proof-criteria-policy-mismatch","proof-criterion-unknown","proof-current-evidence-missing","proof-evidence-digest-mismatch","proof-evidence-id-conflict","proof-protected-authority-required","proof-policy-mismatch","proof-policy-pin-mismatch","proof-self-review-refused","proof-verdict-id-conflict","tenant-scope-denied","ticket-comment-ineligible","ticket-comment-invalid","unauthorized","validation-error","version-conflict","work-assignment-kind-refused","work-assignment-target-ineligible","work-assignment-unchanged","work-priority-unchanged","work-blocker-already-resolved","work-blocker-id-conflict","work-blocker-owner-ineligible","work-blocker-unknown","work-intent-unmet","work-relation-cycle","work-relation-exists","work-reopen-unmet","work-ticket-terminal","workflow-already-started","workflow-pin-mismatch","workflow-predicate-unsatisfied","workflow-run-not-started","proof-incomplete","workflow-state-conflict","workflow-terminal","workflow-transition-not-declared","workflow-version-unknown","workflow-not-terminal"],"type":"string"},"command_id":{"format":"uuid","type":["string","null"]},"current_version":{"minimum":0,"type":["integer","null"]},"detail":{"type":"string"},"status":{"maximum":599,"minimum":400,"type":"integer"},"title":{"type":"string"},"type":{"format":"uri","type":"string"},"unmet_facts":{"items":{"type":"string"},"type":"array"}},"required":["code","detail","status","title","type"],"type":"object"},"ProjectDeliveryCriteria":{"additionalProperties":false,"properties":{"declared":{"minimum":1,"type":"integer"},"proven":{"minimum":0,"type":"integer"}},"required":["proven","declared"],"type":"object"},"ProjectDeliveryRow":{"additionalProperties":false,"properties":{"accountable_owner":{"minLength":1,"type":"string"},"checkpoint_key":{"pattern":"^I[12]\\.[0-9]+$","type":"string"},"checkpoint_label":{"minLength":1,"type":"string"},"confidence":{"enum":["development_degraded","disaster_safe","STATE_UNKNOWN"],"type":"string"},"criteria":{"$ref":"#/components/schemas/ProjectDeliveryCriteria"},"data_class":{"enum":["RECONSTRUCTIBLE_ONLY","DISASTER_SAFE_CTOWER_ENGINEERING","STATE_UNKNOWN"],"type":"string"},"derivation_reasons":{"items":{"minLength":1,"type":"string"},"minItems":1,"type":"array"},"durability":{"enum":["CP3_D_NOT_PROVEN","CP3_D_PROVEN","STATE_UNKNOWN"],"type":"string"},"freshness":{"enum":["fresh","stale","STATE_UNKNOWN"],"type":"string"},"freshness_due_at":{"format":"date-time","type":"string"},"headline_state":{"enum":["planned","in_progress","ready_to_land","merged","verified","released","blocked","done"],"type":"string"},"health":{"enum":["CP3_D_NOT_PROVEN","CURRENT","STATE_UNKNOWN"],"type":"string"},"outcome":{"minLength":1,"type":"string"},"projection_watermark":{"minimum":0,"type":"integer"},"rebuild_generation":{"minimum":0,"type":"integer"},"reconciled_at":{"format":"date-time","type":"string"},"recovery":{"enum":["EXTERNAL_FAILURE_DOMAIN_UNPROVEN","EXTERNAL_FAILURE_DOMAIN_PROVEN","STATE_UNKNOWN"],"type":"string"},"semantic_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"source_ids":{"items":{"minLength":1,"type":"string"},"type":"array"},"source_watermark":{"minimum":0,"type":"integer"},"underlying_maturity":{"enum":["planned","in_progress","ready_to_land","merged","verified","released"],"type":"string"}},"required":["checkpoint_key","checkpoint_label","headline_state","underlying_maturity","outcome","accountable_owner","criteria","source_watermark","projection_watermark","freshness","confidence","health","durability","recovery","data_class","semantic_digest","reconciled_at","freshness_due_at","rebuild_generation","source_ids","derivation_reasons"],"type":"object"},"ProjectDeliveryView":{"additionalProperties":false,"properties":{"company_key":{"pattern":"^[a-z][a-z0-9-]{2,63}$","type":"string"},"freshness_due_at":{"format":"date-time","type":"string"},"project_key":{"pattern":"^[a-z][a-z0-9-]{2,63}$","type":"string"},"projection_record_position":{"minimum":0,"type":"integer"},"projection_semantic_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"rebuild_generation":{"minimum":0,"type":"integer"},"reconciled_at":{"format":"date-time","type":"string"},"rows":{"items":{"$ref":"#/components/schemas/ProjectDeliveryRow"},"type":"array"},"schema":{"const":"ctower.project-delivery/v1"},"source_record_position":{"minimum":0,"type":"integer"}},"required":["schema","company_key","project_key","source_record_position","projection_record_position","reconciled_at","freshness_due_at","projection_semantic_digest","rebuild_generation","rows"],"type":"object"},"ProjectionHealth":{"enum":["CURRENT","STATE_UNKNOWN"],"type":"string"},"ProofChangedAuditEvent":{"additionalProperties":false,"properties":{"actor_principal_id":{"format":"uuid","type":"string"},"command_id":{"format":"uuid","type":"string"},"event_hash":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"event_id":{"format":"uuid","type":"string"},"kind":{"const":"proof.changed"},"occurred_at":{"format":"date-time","type":"string"},"payload":{"$ref":"#/components/schemas/ProofChangedAuditPayload"},"record_position":{"minimum":1,"type":"integer"},"sequence":{"minimum":1,"type":"integer"},"stream_id":{"pattern":"^proof:[0-9a-f-]{36}$","type":"string"}},"required":["actor_principal_id","command_id","event_hash","event_id","kind","occurred_at","payload","record_position","sequence","stream_id"],"type":"object"},"ProofChangedAuditPayload":{"additionalProperties":false,"properties":{"candidate_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"invalidated_evidence_ids":{"items":{"format":"uuid","type":"string"},"type":"array"},"invalidated_verdict_ids":{"items":{"format":"uuid","type":"string"},"type":"array"},"operation":{"enum":["freeze_criteria","record_evidence","record_verdict","change_candidate"],"type":"string"},"proof_version":{"minimum":1,"type":"integer"},"ticket_id":{"format":"uuid","type":"string"}},"required":["candidate_digest","invalidated_evidence_ids","invalidated_verdict_ids","operation","proof_version","ticket_id"],"type":"object"},"ProofCriterion":{"additionalProperties":false,"properties":{"candidate_dependent":{"type":"boolean"},"description":{"maxLength":500,"minLength":1,"type":"string"},"key":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"},"requires_verdict":{"type":"boolean"}},"required":["key","description","candidate_dependent","requires_verdict"],"type":"object"},"ProofReceipt":{"additionalProperties":false,"properties":{"candidate_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"invalidated_evidence_ids":{"items":{"format":"uuid","type":"string"},"type":"array"},"invalidated_verdict_ids":{"items":{"format":"uuid","type":"string"},"type":"array"},"proof_id":{"format":"uuid","type":"string"},"satisfied":{"type":"boolean"},"ticket_id":{"format":"uuid","type":"string"},"version":{"minimum":1,"type":"integer"}},"required":["candidate_digest","command_id","durability_state","event_ids","invalidated_evidence_ids","invalidated_verdict_ids","proof_id","satisfied","ticket_id","version"],"type":"object"},"RelationAddedAuditData":{"additionalProperties":false,"properties":{"reason":{"maxLength":500,"minLength":1,"type":"string"},"relation_kind":{"enum":["parent_of","depends_on","blocks","duplicates","relates_to","caused_by"],"type":"string"},"target_ticket_id":{"format":"uuid","type":"string"}},"required":["relation_kind","reason","target_ticket_id"],"type":"object"},"RelationKind":{"enum":["parent_of","depends_on","blocks","duplicates","relates_to","caused_by"],"type":"string"},"RelationRequest":{"additionalProperties":false,"properties":{"expected_version":{"minimum":1,"type":"integer"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"relation_kind":{"$ref":"#/components/schemas/RelationKind"},"target_ticket_id":{"format":"uuid","type":"string"}},"required":["expected_version","reason","relation_kind","target_ticket_id"],"type":"object"},"ReopenIntent":{"additionalProperties":false,"properties":{"expected_version":{"minimum":1,"type":"integer"},"kind":{"const":"reopen"},"priority_policy":{"const":"carry_forward"},"reason":{"maxLength":500,"minLength":1,"type":"string"}},"required":["kind","expected_version","reason","priority_policy"],"type":"object"},"ReopenedAuditData":{"additionalProperties":false,"properties":{"episode_number":{"minimum":2,"type":"integer"},"priority":{"$ref":"#/components/schemas/Priority"},"reason":{"maxLength":500,"minLength":1,"type":"string"}},"required":["episode_number","priority","reason"],"type":"object"},"ResolveCloseRequest":{"additionalProperties":false,"properties":{"expected_version":{"minimum":1,"type":"integer"},"workflow_ref":{"pattern":"^[a-z][a-z0-9._-]*@[1-9][0-9]*$","type":["string","null"]}},"required":["expected_version"],"type":"object"},"SecretBindingReference":{"additionalProperties":false,"properties":{"name":{"pattern":"^[A-Z][A-Z0-9_]{2,127}$","type":"string"},"reference_class":{"enum":["os-credential","vault-path","runtime-binding"],"type":"string"}},"required":["name","reference_class"],"type":"object"},"SourceReference":{"additionalProperties":false,"properties":{"kind":{"maxLength":64,"minLength":1,"type":"string"},"ref":{"maxLength":256,"minLength":1,"type":"string"}},"required":["kind","ref"],"type":"object"},"SyntheticRunReceipt":{"additionalProperties":false,"properties":{"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"job_id":{"format":"uuid","type":"string"},"run_id":{"format":"uuid","type":"string"},"workflow_ref":{"const":"ctower.trust-spine-four-stage@1"}},"required":["command_id","durability_state","event_ids","job_id","run_id","workflow_ref"],"type":"object"},"SyntheticRunRequest":{"additionalProperties":false,"properties":{"workflow_ref":{"const":"ctower.trust-spine-four-stage@1"}},"required":["workflow_ref"],"type":"object"},"SyntheticRunResource":{"additionalProperties":false,"properties":{"attempt_count":{"maximum":8,"minimum":0,"type":"integer"},"completed_at":{"format":"date-time","type":["string","null"]},"created_at":{"format":"date-time","type":"string"},"detail_code":{"pattern":"^[a-z][a-z0-9._-]{2,95}$","type":["string","null"]},"job_id":{"format":"uuid","type":"string"},"lifecycle_facts":{"items":{"enum":["resolved","closed"],"type":"string"},"maxItems":2,"type":"array"},"run_id":{"format":"uuid","type":"string"},"state":{"$ref":"#/components/schemas/SyntheticRunState"},"ticket_id":{"format":"uuid","type":["string","null"]},"workflow_ref":{"const":"ctower.trust-spine-four-stage@1"}},"required":["attempt_count","completed_at","created_at","detail_code","job_id","lifecycle_facts","run_id","state","ticket_id","workflow_ref"],"type":"object"},"SyntheticRunState":{"enum":["pending","running","succeeded","failed"],"type":"string"},"TelemetryContext":{"additionalProperties":false,"properties":{"actor_id":{"maxLength":128,"minLength":1,"type":"string"},"causation_id":{"maxLength":128,"minLength":1,"type":"string"},"command_id":{"maxLength":128,"minLength":1,"type":"string"},"component_revision_id":{"maxLength":128,"minLength":1,"type":["string","null"]},"correlation_id":{"maxLength":128,"minLength":1,"type":"string"},"deployment_id":{"maxLength":128,"minLength":1,"type":["string","null"]},"effect_id":{"maxLength":128,"minLength":1,"type":["string","null"]},"fencing_token":{"minimum":1,"type":["integer","null"]},"job_id":{"maxLength":128,"minLength":1,"type":["string","null"]},"runner_id":{"maxLength":128,"minLength":1,"type":["string","null"]},"schema":{"const":"ctower.telemetry-context/v1"},"span_id":{"pattern":"^[a-f0-9]{16}$","type":"string"},"stage_attempt_id":{"maxLength":128,"minLength":1,"type":["string","null"]},"tenant_id":{"maxLength":128,"minLength":1,"type":"string"},"ticket_id":{"maxLength":128,"minLength":1,"type":["string","null"]},"trace_flags":{"maximum":255,"minimum":0,"type":"integer"},"trace_id":{"pattern":"^[a-f0-9]{32}$","type":"string"},"trace_state":{"maxLength":512,"type":["string","null"]},"workflow_run_id":{"maxLength":128,"minLength":1,"type":["string","null"]}},"required":["schema","trace_id","span_id","trace_flags","correlation_id","causation_id","tenant_id","actor_id","command_id"],"type":"object"},"TicketCommandResult":{"additionalProperties":false,"properties":{"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"ticket":{"$ref":"#/components/schemas/TicketResource"}},"required":["command_id","durability_state","event_ids","ticket"],"type":"object"},"TicketCommentAddedAuditEvent":{"additionalProperties":false,"properties":{"actor_principal_id":{"format":"uuid","type":"string"},"command_id":{"format":"uuid","type":"string"},"event_hash":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"event_id":{"format":"uuid","type":"string"},"kind":{"const":"ticket.comment_added"},"occurred_at":{"format":"date-time","type":"string"},"payload":{"$ref":"#/components/schemas/TicketCommentAddedPayload"},"record_position":{"minimum":1,"type":"integer"},"sequence":{"minimum":1,"type":"integer"},"stream_id":{"pattern":"^ticket:[0-9a-f-]{36}$","type":"string"}},"required":["actor_principal_id","command_id","event_hash","event_id","kind","occurred_at","payload","record_position","sequence","stream_id"],"type":"object"},"TicketCommentAddedPayload":{"additionalProperties":false,"properties":{"body":{"maxLength":4000,"minLength":1,"type":"string"},"comment_id":{"format":"uuid","type":"string"},"ticket_id":{"format":"uuid","type":"string"}},"required":["body","comment_id","ticket_id"],"type":"object"},"TicketCommentRequest":{"additionalProperties":false,"properties":{"body":{"maxLength":4000,"minLength":1,"type":"string"}},"required":["body"],"type":"object"},"TicketCommentResult":{"additionalProperties":false,"properties":{"command_id":{"format":"uuid","type":"string"},"comment_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_id":{"format":"uuid","type":"string"},"ticket_id":{"format":"uuid","type":"string"}},"required":["command_id","comment_id","durability_state","event_id","ticket_id"],"type":"object"},"TicketCreateRequest":{"additionalProperties":false,"properties":{"initial_custodian_id":{"format":"uuid","type":["string","null"]},"priority":{"$ref":"#/components/schemas/Priority"},"source":{"$ref":"#/components/schemas/SourceReference"},"title":{"maxLength":200,"minLength":1,"type":"string"}},"required":["priority","source","title"],"type":"object"},"TicketCreatedAuditEvent":{"additionalProperties":false,"properties":{"actor_principal_id":{"format":"uuid","type":"string"},"command_id":{"format":"uuid","type":"string"},"event_hash":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"event_id":{"format":"uuid","type":"string"},"kind":{"const":"ticket.created"},"occurred_at":{"format":"date-time","type":"string"},"payload":{"$ref":"#/components/schemas/TicketCreatedPayload"},"record_position":{"minimum":1,"type":"integer"},"sequence":{"minimum":1,"type":"integer"},"stream_id":{"pattern":"^ticket:[0-9a-f-]{36}$","type":"string"}},"required":["actor_principal_id","command_id","event_hash","event_id","kind","occurred_at","payload","record_position","sequence","stream_id"],"type":"object"},"TicketCreatedPayload":{"additionalProperties":false,"properties":{"custodian_id":{"format":"uuid","type":"string"},"priority":{"$ref":"#/components/schemas/Priority"},"source_kind":{"maxLength":64,"minLength":1,"type":"string"},"source_ref":{"maxLength":256,"minLength":1,"type":"string"},"title":{"type":"string"}},"required":["custodian_id","priority","source_kind","source_ref","title"],"type":"object"},"TicketIntentRequest":{"additionalProperties":false,"properties":{"intent":{"oneOf":[{"$ref":"#/components/schemas/AdmitIntent"},{"$ref":"#/components/schemas/DeferIntent"},{"$ref":"#/components/schemas/BlockIntent"},{"$ref":"#/components/schemas/UnblockIntent"},{"$ref":"#/components/schemas/ReopenIntent"}]}},"required":["intent"],"type":"object"},"TicketResource":{"additionalProperties":false,"properties":{"created_at":{"format":"date-time","type":"string"},"custodian_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"priority":{"$ref":"#/components/schemas/Priority"},"source":{"$ref":"#/components/schemas/SourceReference"},"ticket_id":{"format":"uuid","type":"string"},"title":{"type":"string"},"version":{"minimum":1,"type":"integer"}},"required":["created_at","custodian_id","durability_state","priority","source","ticket_id","title","version"],"type":"object"},"TimelineEvent":{"additionalProperties":false,"properties":{"actor_principal_id":{"format":"uuid","type":"string"},"command_id":{"format":"uuid","type":"string"},"event_id":{"format":"uuid","type":"string"},"kind":{"enum":["ticket.created","ticket.custody_transferred","ticket.comment_added"],"type":"string"},"occurred_at":{"format":"date-time","type":"string"},"payload":{"oneOf":[{"$ref":"#/components/schemas/TicketCreatedPayload"},{"$ref":"#/components/schemas/CustodyTransferredPayload"},{"$ref":"#/components/schemas/TicketCommentAddedPayload"}]},"sequence":{"minimum":1,"type":"integer"}},"required":["actor_principal_id","command_id","event_id","kind","occurred_at","payload","sequence"],"type":"object"},"TimelineResponse":{"additionalProperties":false,"properties":{"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"events":{"items":{"$ref":"#/components/schemas/TimelineEvent"},"type":"array"},"ticket_id":{"format":"uuid","type":"string"}},"required":["durability_state","events","ticket_id"],"type":"object"},"UnblockIntent":{"additionalProperties":false,"properties":{"blocker_id":{"format":"uuid","type":"string"},"expected_version":{"minimum":1,"type":"integer"},"kind":{"const":"unblock"},"reason":{"maxLength":500,"minLength":1,"type":"string"},"resolution_evidence_ref":{"maxLength":256,"minLength":1,"type":"string"}},"required":["kind","expected_version","reason","blocker_id","resolution_evidence_ref"],"type":"object"},"VerdictDecision":{"enum":["pass","fail"],"type":"string"},"VerdictRequest":{"additionalProperties":false,"properties":{"candidate_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"criterion_key":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"},"decision":{"$ref":"#/components/schemas/VerdictDecision"},"expected_version":{"minimum":1,"type":"integer"},"verdict_id":{"format":"uuid","type":"string"}},"required":["expected_version","verdict_id","criterion_key","candidate_digest","decision"],"type":"object"},"VersionedComponent":{"additionalProperties":false,"properties":{"compatibility":{"$ref":"#/components/schemas/ComponentCompatibility"},"content_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"key":{"pattern":"^[a-z][a-z0-9.-]{2,127}$","type":"string"},"kind":{"$ref":"#/components/schemas/ComponentKind"},"lifecycle":{"enum":["draft","published","deprecated","revoked"],"type":"string"},"payload_ref":{"pattern":"^object:sha256:[0-9a-f]{64}$","type":"string"},"provenance":{"items":{"$ref":"#/components/schemas/ComponentProvenance"},"maxItems":64,"minItems":1,"type":"array"},"revision":{"minimum":1,"type":"integer"},"schema":{"const":"ctower.versioned-component/v1"},"schema_ref":{"pattern":"^ctower\\.[a-z][a-z0-9.-]*/v[1-9][0-9]*$","type":"string"},"scope":{"$ref":"#/components/schemas/ComponentScope"},"supersedes":{"$ref":"#/components/schemas/ComponentReference"}},"required":["compatibility","content_digest","key","kind","lifecycle","payload_ref","provenance","revision","schema","schema_ref","scope"],"type":"object"},"WorkAdmittedAuditPayload":{"additionalProperties":false,"properties":{"data":{"$ref":"#/components/schemas/AdmittedAuditData"},"operation":{"const":"admitted"},"ticket_id":{"format":"uuid","type":"string"},"work_version":{"minimum":2,"type":"integer"}},"required":["data","operation","ticket_id","work_version"],"type":"object"},"WorkAssignmentChangedAuditPayload":{"additionalProperties":false,"properties":{"data":{"$ref":"#/components/schemas/AssignmentChangedAuditData"},"operation":{"const":"assignment_changed"},"ticket_id":{"format":"uuid","type":"string"},"work_version":{"minimum":2,"type":"integer"}},"required":["data","operation","ticket_id","work_version"],"type":"object"},"WorkBlockerOpenedAuditPayload":{"additionalProperties":false,"properties":{"data":{"$ref":"#/components/schemas/BlockerOpenedAuditData"},"operation":{"const":"blocker_opened"},"ticket_id":{"format":"uuid","type":"string"},"work_version":{"minimum":2,"type":"integer"}},"required":["data","operation","ticket_id","work_version"],"type":"object"},"WorkBlockerResolvedAuditPayload":{"additionalProperties":false,"properties":{"data":{"$ref":"#/components/schemas/BlockerResolvedAuditData"},"operation":{"const":"blocker_resolved"},"ticket_id":{"format":"uuid","type":"string"},"work_version":{"minimum":2,"type":"integer"}},"required":["data","operation","ticket_id","work_version"],"type":"object"},"WorkChangedAuditEvent":{"additionalProperties":false,"properties":{"actor_principal_id":{"format":"uuid","type":"string"},"command_id":{"format":"uuid","type":"string"},"event_hash":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"event_id":{"format":"uuid","type":"string"},"kind":{"const":"work.changed"},"occurred_at":{"format":"date-time","type":"string"},"payload":{"$ref":"#/components/schemas/WorkChangedAuditPayload"},"record_position":{"minimum":1,"type":"integer"},"sequence":{"minimum":1,"type":"integer"},"stream_id":{"pattern":"^ticket:[0-9a-f-]{36}$","type":"string"}},"required":["actor_principal_id","command_id","event_hash","event_id","kind","occurred_at","payload","record_position","sequence","stream_id"],"type":"object"},"WorkChangedAuditPayload":{"oneOf":[{"$ref":"#/components/schemas/WorkPriorityChangedAuditPayload"},{"$ref":"#/components/schemas/WorkAssignmentChangedAuditPayload"},{"$ref":"#/components/schemas/WorkAdmittedAuditPayload"},{"$ref":"#/components/schemas/WorkDeferredAuditPayload"},{"$ref":"#/components/schemas/WorkBlockerOpenedAuditPayload"},{"$ref":"#/components/schemas/WorkBlockerResolvedAuditPayload"},{"$ref":"#/components/schemas/WorkReopenedAuditPayload"},{"$ref":"#/components/schemas/WorkRelationAddedAuditPayload"}]},"WorkDeferredAuditPayload":{"additionalProperties":false,"properties":{"data":{"$ref":"#/components/schemas/DeferredAuditData"},"operation":{"const":"deferred"},"ticket_id":{"format":"uuid","type":"string"},"work_version":{"minimum":2,"type":"integer"}},"required":["data","operation","ticket_id","work_version"],"type":"object"},"WorkPriorityChangedAuditPayload":{"additionalProperties":false,"properties":{"data":{"$ref":"#/components/schemas/PriorityChangedAuditData"},"operation":{"const":"priority_changed"},"ticket_id":{"format":"uuid","type":"string"},"work_version":{"minimum":2,"type":"integer"}},"required":["data","operation","ticket_id","work_version"],"type":"object"},"WorkReceipt":{"additionalProperties":false,"properties":{"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"operation":{"enum":["priority_changed","assignment_changed","admitted","deferred","blocker_opened","blocker_resolved","reopened","relation_added"],"type":"string"},"ticket_id":{"format":"uuid","type":"string"},"version":{"minimum":2,"type":"integer"}},"required":["command_id","durability_state","event_ids","operation","ticket_id","version"],"type":"object"},"WorkRelationAddedAuditPayload":{"additionalProperties":false,"properties":{"data":{"$ref":"#/components/schemas/RelationAddedAuditData"},"operation":{"const":"relation_added"},"ticket_id":{"format":"uuid","type":"string"},"work_version":{"minimum":2,"type":"integer"}},"required":["data","operation","ticket_id","work_version"],"type":"object"},"WorkReopenedAuditPayload":{"additionalProperties":false,"properties":{"data":{"$ref":"#/components/schemas/ReopenedAuditData"},"operation":{"const":"reopened"},"ticket_id":{"format":"uuid","type":"string"},"work_version":{"minimum":2,"type":"integer"}},"required":["data","operation","ticket_id","work_version"],"type":"object"},"WorkflowChangedAuditEvent":{"additionalProperties":false,"properties":{"actor_principal_id":{"format":"uuid","type":"string"},"command_id":{"format":"uuid","type":"string"},"event_hash":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"event_id":{"format":"uuid","type":"string"},"kind":{"const":"workflow.changed"},"occurred_at":{"format":"date-time","type":"string"},"payload":{"$ref":"#/components/schemas/WorkflowChangedAuditPayload"},"record_position":{"minimum":1,"type":"integer"},"sequence":{"minimum":1,"type":"integer"},"stream_id":{"pattern":"^workflow:[0-9a-f-]{36}$","type":"string"}},"required":["actor_principal_id","command_id","event_hash","event_id","kind","occurred_at","payload","record_position","sequence","stream_id"],"type":"object"},"WorkflowChangedAuditPayload":{"additionalProperties":false,"properties":{"lifecycle_facts":{"items":{"enum":["resolved","closed"],"type":"string"},"maxItems":2,"type":"array"},"operation":{"enum":["start","transition","resolve_close"],"type":"string"},"stage":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"},"ticket_id":{"format":"uuid","type":"string"},"workflow_ref":{"pattern":"^[a-z][a-z0-9._-]*@[1-9][0-9]*$","type":"string"},"workflow_version":{"minimum":1,"type":"integer"}},"required":["lifecycle_facts","operation","stage","ticket_id","workflow_ref","workflow_version"],"type":"object"},"WorkflowReceipt":{"additionalProperties":false,"properties":{"activity_class":{"$ref":"#/components/schemas/ActivityClass"},"command_id":{"format":"uuid","type":"string"},"durability_state":{"$ref":"#/components/schemas/DurabilityState"},"event_ids":{"items":{"format":"uuid","type":"string"},"minItems":1,"type":"array"},"lifecycle_facts":{"items":{"enum":["resolved","closed"],"type":"string"},"maxItems":2,"type":"array"},"stage":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"},"ticket_id":{"format":"uuid","type":"string"},"version":{"minimum":1,"type":"integer"},"workflow_ref":{"pattern":"^[a-z][a-z0-9._-]*@[1-9][0-9]*$","type":"string"},"workflow_run_id":{"format":"uuid","type":"string"}},"required":["activity_class","command_id","durability_state","event_ids","lifecycle_facts","stage","ticket_id","version","workflow_ref","workflow_run_id"],"type":"object"},"WorkflowStartRequest":{"additionalProperties":false,"properties":{"evidence_policy_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"evidence_policy_ref":{"pattern":"^[a-z][a-z0-9._-]*@[1-9][0-9]*$","type":"string"},"execution_policy_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"execution_policy_ref":{"pattern":"^[a-z][a-z0-9._-]*@[1-9][0-9]*$","type":"string"},"gate_policy_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"gate_policy_ref":{"pattern":"^[a-z][a-z0-9._-]*@[1-9][0-9]*$","type":"string"},"workflow_digest":{"pattern":"^sha256:[0-9a-f]{64}$","type":"string"},"workflow_ref":{"pattern":"^[a-z][a-z0-9._-]*@[1-9][0-9]*$","type":"string"}},"required":["workflow_ref","workflow_digest","execution_policy_ref","execution_policy_digest","gate_policy_ref","gate_policy_digest","evidence_policy_ref","evidence_policy_digest"],"type":"object"},"WorkflowTransitionRequest":{"additionalProperties":false,"properties":{"destination_stage":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"},"expected_version":{"minimum":0,"type":"integer"},"source_stage":{"pattern":"^[a-z][a-z0-9._-]*$","type":"string"},"workflow_ref":{"pattern":"^[a-z][a-z0-9._-]*@[1-9][0-9]*$","type":"string"}},"required":["expected_version","workflow_ref","source_stage","destination_stage"],"type":"object"}};
export const OPERATION_SUCCESS_MODELS: Readonly<
  Record<OperationId, Readonly<Record<string, string>>>
> = {"addTicketComment":{"200":"TicketCommentResult","202":"TicketCommentResult"},"addTicketRelation":{"200":"WorkReceipt","202":"WorkReceipt"},"appendCtowerProjectImportCorrection":{"201":"CtowerProjectMigrationReceipt","202":"CtowerProjectMigrationReceipt"},"applyCompanyBundle":{"200":"CompanyBundleCommandResult","202":"CompanyBundleCommandResult"},"applyCtowerProjectImportBatch":{"200":"CtowerProjectImportBatchResult","202":"CtowerProjectImportBatchResult"},"applyTicketIntent":{"200":"WorkReceipt","202":"WorkReceipt"},"bindCtowerProjectAliasPlan":{"200":"CtowerProjectImportRun","202":"CtowerProjectImportRun"},"bindCtowerProjectExportEquality":{"200":"CtowerProjectImportRun","202":"CtowerProjectImportRun"},"bootstrapFirstTenant":{"201":"BootstrapReceipt","202":"BootstrapReceipt"},"changeTicketAssignment":{"200":"WorkReceipt","202":"WorkReceipt"},"changeTicketPriority":{"200":"WorkReceipt","202":"WorkReceipt"},"commitCtowerProjectDevelopmentEpoch":{},"createCtowerProjectImportRun":{"201":"CtowerProjectImportRun","202":"CtowerProjectImportRun"},"createTicket":{"201":"TicketCommandResult","202":"TicketCommandResult"},"exportCompanyBundle":{"200":"CompanyBundleExportResult"},"finalizeCtowerProjectImportRun":{"200":"CtowerProjectReconciliationResult","202":"CtowerProjectReconciliationResult"},"freezeProofCriteria":{"200":"ProofReceipt","202":"ProofReceipt"},"getBoard":{"200":"BoardView"},"getControlHealth":{"200":"ControlHealth"},"getCtowerProjectCutoverHealth":{"200":"CtowerProjectCutoverHealth"},"getCtowerProjectImportRun":{"200":"CtowerProjectImportRun"},"getProjectDelivery":{"200":"ProjectDeliveryView"},"getSyntheticWorkflowRun":{"200":"SyntheticRunResource"},"getTicket":{"200":"TicketResource"},"getTicketTimeline":{"200":"TimelineResponse"},"listTicketAssignments":{"200":"AssignmentList"},"listTicketAuditEvents":{"200":"AuditPage"},"planCompanyBundle":{"200":"CompanyBundlePlan"},"prepareCtowerProjectCutover":{},"promoteIntakeEvent":{"200":"IntakeCommandResult","202":"IntakeCommandResult"},"recordOutboxPoisonDisposition":{"200":"PoisonDispositionReceipt","202":"PoisonDispositionReceipt"},"recordProofEvidence":{"200":"ProofReceipt","202":"ProofReceipt"},"recordProofVerdict":{"200":"ProofReceipt","202":"ProofReceipt"},"reportCtowerProjectFenceObservation":{"201":"CtowerProjectMigrationReceipt","202":"CtowerProjectMigrationReceipt"},"resolveCloseWorkflow":{"200":"WorkflowReceipt","202":"WorkflowReceipt"},"runSyntheticWorkflow":{"201":"SyntheticRunReceipt","202":"SyntheticRunReceipt"},"startTicketWorkflow":{"200":"WorkflowReceipt","202":"WorkflowReceipt"},"submitIntake":{"201":"IntakeCommandResult","202":"IntakeCommandResult"},"transferTicketCustody":{"200":"TicketCommandResult","202":"TicketCommandResult"},"transitionWorkflow":{"200":"WorkflowReceipt","202":"WorkflowReceipt"},"validateCompanyBundle":{"200":"CompanyBundleValidationResult"}};
export const OPERATION_PROBLEM_MODELS: Readonly<
  Record<OperationId, Readonly<Record<string, string>>>
> = {"addTicketComment":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","422":"Problem"},"addTicketRelation":{"401":"Problem","404":"Problem","409":"Problem","422":"Problem"},"appendCtowerProjectImportCorrection":{"401":"Problem","409":"Problem","422":"Problem"},"applyCompanyBundle":{"401":"Problem","403":"Problem","409":"Problem","422":"Problem","503":"Problem"},"applyCtowerProjectImportBatch":{"401":"Problem","403":"Problem","409":"Problem","422":"Problem"},"applyTicketIntent":{"401":"Problem","404":"Problem","409":"Problem","422":"Problem"},"bindCtowerProjectAliasPlan":{"401":"Problem","409":"Problem","422":"Problem"},"bindCtowerProjectExportEquality":{"401":"Problem","409":"Problem","422":"Problem"},"bootstrapFirstTenant":{"401":"Problem","403":"Problem","409":"Problem","410":"Problem","422":"Problem"},"changeTicketAssignment":{"401":"Problem","404":"Problem","409":"Problem","422":"Problem"},"changeTicketPriority":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","422":"Problem"},"commitCtowerProjectDevelopmentEpoch":{"401":"Problem","409":"Problem","422":"Problem"},"createCtowerProjectImportRun":{"401":"Problem","409":"Problem","422":"Problem"},"createTicket":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","422":"Problem"},"exportCompanyBundle":{"401":"Problem","403":"Problem","404":"Problem"},"finalizeCtowerProjectImportRun":{"401":"Problem","409":"Problem","422":"Problem"},"freezeProofCriteria":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","422":"Problem"},"getBoard":{"401":"Problem","422":"Problem"},"getControlHealth":{"401":"Problem"},"getCtowerProjectCutoverHealth":{"401":"Problem"},"getCtowerProjectImportRun":{"401":"Problem","404":"Problem"},"getProjectDelivery":{"401":"Problem","404":"Problem","422":"Problem"},"getSyntheticWorkflowRun":{"401":"Problem","404":"Problem","422":"Problem"},"getTicket":{"401":"Problem","404":"Problem","422":"Problem"},"getTicketTimeline":{"401":"Problem","404":"Problem","422":"Problem"},"listTicketAssignments":{"401":"Problem","404":"Problem","422":"Problem"},"listTicketAuditEvents":{"401":"Problem","404":"Problem","422":"Problem"},"planCompanyBundle":{"401":"Problem","403":"Problem","409":"Problem","422":"Problem"},"prepareCtowerProjectCutover":{"401":"Problem","409":"Problem","422":"Problem"},"promoteIntakeEvent":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","413":"Problem","422":"Problem"},"recordOutboxPoisonDisposition":{"401":"Problem","404":"Problem","409":"Problem","422":"Problem"},"recordProofEvidence":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","422":"Problem"},"recordProofVerdict":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","422":"Problem"},"reportCtowerProjectFenceObservation":{"401":"Problem","403":"Problem","409":"Problem","422":"Problem"},"resolveCloseWorkflow":{"401":"Problem","404":"Problem","409":"Problem","422":"Problem"},"runSyntheticWorkflow":{"401":"Problem","403":"Problem","409":"Problem","422":"Problem"},"startTicketWorkflow":{"401":"Problem","404":"Problem","409":"Problem","422":"Problem"},"submitIntake":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","413":"Problem","422":"Problem"},"transferTicketCustody":{"401":"Problem","403":"Problem","404":"Problem","409":"Problem","422":"Problem"},"transitionWorkflow":{"401":"Problem","404":"Problem","409":"Problem","422":"Problem"},"validateCompanyBundle":{"401":"Problem","403":"Problem","422":"Problem"}};

export function decodeOperationResult(
  operationId: OperationId,
  status: number,
  node: JsonNode,
): unknown {
  const model = OPERATION_SUCCESS_MODELS[operationId][String(status)];
  if (model === undefined) return fail(operationId, `undeclared success status ${status}`);
  return decodeNamed(model, node, operationId);
}

export function decodeOperationProblem(
  operationId: OperationId,
  status: number,
  node: JsonNode,
): unknown {
  const model = OPERATION_PROBLEM_MODELS[operationId][String(status)];
  if (model === undefined) return fail(operationId, `undeclared problem status ${status}`);
  const path = `${operationId}.problem`;
  const problem = objectValue(decodeNamed(model, node, path), path);
  if (problem["status"] !== status) {
    return fail(`${path}.status`, "Problem status does not match HTTP status");
  }
  return problem;
}

function decodeNamed(name: string, node: JsonNode, path: string): unknown {
  const schema = SCHEMAS[name];
  if (schema === undefined) return fail(path, `unknown schema ${name}`);
  return decodeSchema(schema, node, path);
}

function decodeSchema(schemaValue: unknown, node: JsonNode, path: string): unknown {
  const schema = objectValue(schemaValue, `${path}.schema`);
  const reference = schema["$ref"];
  if (typeof reference === "string") {
    return decodeNamed(referenceName(reference, path), node, path);
  }
  const oneOf = schema["oneOf"];
  if (Array.isArray(oneOf)) return decodeOneOf(oneOf, node, path);
  const declaredType = schema["type"];
  let value: unknown;
  if (Array.isArray(declaredType)) {
    value = decodeTypeUnion(schema, declaredType, node, path);
  } else if (typeof declaredType === "string") {
    value = decodeTyped(schema, declaredType, node, path);
  } else {
    value = decodeImplicitScalar(schema, node, path);
  }
  validateConstAndEnum(schema, value, path);
  return value;
}

function decodeOneOf(
  branches: ReadonlyArray<unknown>,
  node: JsonNode,
  path: string,
): unknown {
  const matches: unknown[] = [];
  for (const branch of branches) {
    try {
      matches.push(decodeSchema(branch, node, path));
    } catch (error: unknown) {
      if (!(error instanceof TypeError)) throw error;
    }
  }
  if (matches.length !== 1) return fail(path, "value must match exactly one schema");
  return matches[0];
}

function decodeTypeUnion(
  schema: SchemaObject,
  types: ReadonlyArray<unknown>,
  node: JsonNode,
  path: string,
): unknown {
  for (const kind of types) {
    if (typeof kind !== "string") continue;
    try {
      return decodeTyped(schema, kind, node, path);
    } catch (error: unknown) {
      if (!(error instanceof TypeError)) throw error;
    }
  }
  return fail(path, "value has the wrong type");
}

function decodeImplicitScalar(
  schema: SchemaObject,
  node: JsonNode,
  path: string,
): unknown {
  const choices = schema["enum"];
  const exemplar = "const" in schema
    ? schema["const"]
    : Array.isArray(choices) && choices.length > 0
      ? choices[0]
      : undefined;
  if (typeof exemplar === "string") return decodeString(schema, node, path);
  if (typeof exemplar === "boolean") return decodeBoolean(node, path);
  if (exemplar === null) return decodeNull(node, path);
  if (typeof exemplar === "number" && Number.isInteger(exemplar)) {
    return decodeInteger(schema, node, path);
  }
  if (typeof exemplar === "number") return decodeNumber(schema, node, path);
  return fail(path, "schema has no materializable scalar type");
}

function decodeTyped(
  schema: SchemaObject,
  kind: string,
  node: JsonNode,
  path: string,
): unknown {
  if (kind === "null") return decodeNull(node, path);
  if (kind === "boolean") return decodeBoolean(node, path);
  if (kind === "string") return decodeString(schema, node, path);
  if (kind === "integer") return decodeInteger(schema, node, path);
  if (kind === "number") return decodeNumber(schema, node, path);
  if (kind === "array") return decodeArray(schema, node, path);
  if (kind === "object") return decodeObject(schema, node, path);
  return fail(path, `unsupported schema type ${kind}`);
}

function decodeNull(node: JsonNode, path: string): null {
  if (node !== null) return fail(path, "value is not null");
  return null;
}

function decodeBoolean(node: JsonNode, path: string): boolean {
  if (typeof node !== "boolean") return fail(path, "value is not a boolean");
  return node;
}

function decodeString(schema: SchemaObject, node: JsonNode, path: string): string {
  if (typeof node !== "string") return fail(path, "value is not a string");
  const minimum = schema["minLength"];
  const maximum = schema["maxLength"];
  if (typeof minimum === "number" && node.length < minimum) fail(path, "string is too short");
  if (typeof maximum === "number" && node.length > maximum) fail(path, "string is too long");
  const pattern = schema["pattern"];
  if (typeof pattern === "string" && !new RegExp(pattern, "u").test(node)) {
    fail(path, "string does not match pattern");
  }
  validateFormat(schema["format"], node, path);
  return node;
}

function decodeInteger(schema: SchemaObject, node: JsonNode, path: string): number {
  const number = numberNode(node, path);
  if (!/^-?(?:0|[1-9][0-9]*)$/u.test(number.raw)) {
    return fail(path, "value is not an exact JSON integer token");
  }
  if (!integerTokenInSharedRange(number.raw)) {
    return fail(path, "integer is outside the lossless JSON range");
  }
  const value = number.raw === "-0" ? 0 : Number(number.raw);
  validateNumericBounds(schema, value, path);
  return value;
}

function decodeNumber(schema: SchemaObject, node: JsonNode, path: string): number {
  const value = Number(numberNode(node, path).raw);
  if (!Number.isFinite(value)) return fail(path, "number is not finite");
  validateNumericBounds(schema, value, path);
  return value;
}

function integerTokenInSharedRange(raw: string): boolean {
  const negative = raw.startsWith("-");
  const digits = negative ? raw.slice(1) : raw;
  const limit = String(negative ? -JSON_INTEGER_MINIMUM : JSON_INTEGER_MAXIMUM);
  return digits.length < limit.length || digits.length === limit.length && digits <= limit;
}

function validateNumericBounds(schema: SchemaObject, value: number, path: string): void {
  const minimum = schema["minimum"];
  const maximum = schema["maximum"];
  if (typeof minimum === "number" && value < minimum) fail(path, "number is below minimum");
  if (typeof maximum === "number" && value > maximum) fail(path, "number is above maximum");
}

function decodeArray(schema: SchemaObject, node: JsonNode, path: string): unknown[] {
  const array = arrayNode(node, path);
  const minimum = schema["minItems"];
  const maximum = schema["maxItems"];
  if (typeof minimum === "number" && array.items.length < minimum) {
    fail(path, "array has too few items");
  }
  if (typeof maximum === "number" && array.items.length > maximum) {
    fail(path, "array has too many items");
  }
  const items = schema["items"];
  if (items === undefined) return fail(path, "array schema has unconstrained items");
  return array.items.map((item, index) => decodeSchema(items, item, `${path}[${index}]`));
}

function decodeObject(
  schema: SchemaObject,
  node: JsonNode,
  path: string,
): Record<string, unknown> {
  const object = objectNode(node, path);
  const properties = objectValue(schema["properties"] ?? {}, `${path}.properties`);
  const members = new Map<string, JsonNode>();
  for (const [name, member] of object.members) members.set(name, member);
  const required = schema["required"];
  if (Array.isArray(required)) {
    for (const name of required) {
      if (typeof name !== "string" || !members.has(name)) {
        fail(path, `missing required field ${String(name)}`);
      }
    }
  }
  const result: Record<string, unknown> = {};
  for (const [name, member] of members) {
    let value: unknown;
    if (Object.hasOwn(properties, name)) {
      value = decodeSchema(properties[name], member, `${path}.${name}`);
    } else {
      const additional = schema["additionalProperties"];
      if (additional === false) fail(path, `unknown field ${name}`);
      if (hasFreeFormAdditionalProperties(additional)) {
        value = decodeUntyped(member, `${path}.${name}`);
      } else {
        value = decodeSchema(additional, member, `${path}.${name}`);
      }
    }
    Object.defineProperty(result, name, {
      configurable: true,
      enumerable: true,
      value,
      writable: true,
    });
  }
  return result;
}

function hasFreeFormAdditionalProperties(value: unknown): boolean {
  return (
    value === undefined ||
    value === true ||
    value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.keys(value).length === 0
  );
}

const FREE_FORM_NUMBER_SCHEMA: SchemaObject = Object.freeze({});

function decodeUntyped(node: JsonNode, path: string): unknown {
  if (node === null || typeof node === "string" || typeof node === "boolean") return node;
  if (node.kind === "number") {
    return /[.eE]/u.test(node.raw)
      ? decodeNumber(FREE_FORM_NUMBER_SCHEMA, node, path)
      : decodeInteger(FREE_FORM_NUMBER_SCHEMA, node, path);
  }
  if (node.kind === "array") {
    return node.items.map((item, index) => decodeUntyped(item, `${path}[${index}]`));
  }
  const members = new Map<string, JsonNode>();
  for (const [name, member] of node.members) members.set(name, member);
  const result: Record<string, unknown> = {};
  for (const [name, member] of members) {
    Object.defineProperty(result, name, {
      configurable: true,
      enumerable: true,
      value: decodeUntyped(member, `${path}.${name}`),
      writable: true,
    });
  }
  return result;
}

function validateConstAndEnum(schema: SchemaObject, value: unknown, path: string): void {
  if ("const" in schema && !Object.is(value, schema["const"])) {
    fail(path, "value does not equal const");
  }
  const choices = schema["enum"];
  if (Array.isArray(choices) && !choices.some((choice) => Object.is(choice, value))) {
    fail(path, "value is outside enum");
  }
}

function validateFormat(format: unknown, value: string, path: string): void {
  if (format === "uuid" && !UUID_PATTERN.test(value)) fail(path, "string is not a UUID");
  if (format === "date-time") validateDateTime(value, path);
  if (format === "uri" && !isAbsoluteUri(value)) fail(path, "string is not an absolute URI");
}

function validateDateTime(value: string, path: string): void {
  const match = DATE_TIME_PATTERN.exec(value);
  if (match === null || match[7] === "-00:00") {
    fail(path, "string is outside the authored RFC 3339 profile");
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth(year, month) ||
    hour > 23 ||
    minute > 59 ||
    second > 59
  ) fail(path, "string is outside the proleptic Gregorian calendar");
  const offsetHour = Number(match[9] ?? 0);
  const offsetMinute = Number(match[10] ?? 0);
  if (offsetHour > 23 || offsetMinute > 59) {
    fail(path, "string has an invalid RFC 3339 numeric offset");
  }
}

function daysInMonth(year: number, month: number): number {
  if (month === 2) {
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    return leap ? 29 : 28;
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

function numberNode(node: JsonNode, path: string): JsonNumberNode {
  if (node === null || typeof node !== "object" || node.kind !== "number") {
    return fail(path, "value is not a number");
  }
  return node;
}

function arrayNode(node: JsonNode, path: string): JsonArrayNode {
  if (node === null || typeof node !== "object" || node.kind !== "array") {
    return fail(path, "value is not an array");
  }
  return node;
}

function objectNode(node: JsonNode, path: string): JsonObjectNode {
  if (node === null || typeof node !== "object" || node.kind !== "object") {
    return fail(path, "value is not an object");
  }
  return node;
}

function objectValue(value: unknown, path: string): SchemaObject {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return fail(path, "value is not an object");
  }
  return value as SchemaObject;
}

function referenceName(reference: string, path: string): string {
  const prefix = "#/components/schemas/";
  if (!reference.startsWith(prefix)) return fail(path, `unsupported reference ${reference}`);
  return reference.slice(prefix.length);
}

function fail(path: string, reason: string): never {
  throw new TypeError(`Invalid ctower response at ${path}: ${reason}`);
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;
const DATE_TIME_PATTERN =
  /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]{1,6})?(Z|([+-])([0-9]{2}):([0-9]{2}))$/u;

const URI_UNRESERVED = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
const URI_SUB_DELIMITERS = "!$&'()*+,;=";
const URI_HEX_DIGITS = '0123456789ABCDEFabcdef';
const URI_PCHAR = URI_UNRESERVED + URI_SUB_DELIMITERS + ":@";

function isAbsoluteUri(value: string): boolean {
  if (value.length === 0) return false;
  for (const char of value) {
    const code = char.charCodeAt(0);
    if (code <= 32 || code >= 127 || char === "\\") return false;
  }
  const colon = value.indexOf(":");
  if (colon <= 0 || !isUriScheme(value.slice(0, colon))) return false;
  const scheme = value.slice(0, colon);
  let remainder = value.slice(colon + 1);
  const fragmentAt = remainder.indexOf("#");
  if (fragmentAt >= 0) {
    const fragment = remainder.slice(fragmentAt + 1);
    remainder = remainder.slice(0, fragmentAt);
    if (!validUriComponent(fragment, true, true)) return false;
  }
  const queryAt = remainder.indexOf("?");
  if (queryAt >= 0) {
    const query = remainder.slice(queryAt + 1);
    remainder = remainder.slice(0, queryAt);
    if (!validUriComponent(query, true, true)) return false;
  }
  const hasAuthority = remainder.startsWith("//");
  let host = "";
  let path: string;
  if (hasAuthority) {
    const authorityAndPath = remainder.slice(2);
    const slashAt = authorityAndPath.indexOf("/");
    const authority = slashAt < 0 ? authorityAndPath : authorityAndPath.slice(0, slashAt);
    path = slashAt < 0 ? "" : authorityAndPath.slice(slashAt);
    const parsed = parseUriAuthority(authority);
    if (!parsed[0]) return false;
    host = parsed[1];
  } else {
    path = remainder;
  }
  if (!validUriComponent(path, true, false)) return false;
  const lowerScheme = scheme.toLowerCase();
  return lowerScheme !== "http" && lowerScheme !== "https" || hasAuthority && host.length > 0;
}

function isUriScheme(value: string): boolean {
  if (value.length === 0 || !asciiAlpha(value[0] ?? "")) return false;
  for (const char of value.slice(1)) {
    if (!asciiAlpha(char) && !asciiDigit(char) && !"+-.".includes(char)) return false;
  }
  return true;
}

function validUriComponent(
  value: string,
  allowSlash: boolean,
  allowQuestion: boolean,
): boolean {
  const allowed = URI_PCHAR + (allowSlash ? "/" : "") + (allowQuestion ? "?" : "");
  return validUriToken(value, allowed);
}

function validUriToken(value: string, allowed: string): boolean {
  let index = 0;
  while (index < value.length) {
    const char = value[index] ?? "";
    if (char === "%") {
      if (
        index + 2 >= value.length ||
        !URI_HEX_DIGITS.includes(value[index + 1] ?? "") ||
        !URI_HEX_DIGITS.includes(value[index + 2] ?? "")
      ) return false;
      index += 3;
    } else if (allowed.includes(char)) {
      index += 1;
    } else {
      return false;
    }
  }
  return true;
}

function parseUriAuthority(value: string): readonly [boolean, string] {
  if (value.split("@").length > 2) return [false, ""];
  let hostPort = value;
  const at = value.lastIndexOf("@");
  if (at >= 0) {
    const userinfo = value.slice(0, at);
    hostPort = value.slice(at + 1);
    if (!validUriToken(userinfo, URI_UNRESERVED + URI_SUB_DELIMITERS + ":")) {
      return [false, ""];
    }
  }
  if (hostPort.startsWith("[")) {
    const close = hostPort.indexOf("]");
    if (close < 0 || !validIpLiteral(hostPort.slice(1, close))) return [false, ""];
    const suffix = hostPort.slice(close + 1);
    if (suffix.length > 0 && (!suffix.startsWith(":") || !validPort(suffix.slice(1)))) {
      return [false, ""];
    }
    return [true, hostPort.slice(0, close + 1)];
  }
  if (hostPort.includes("[") || hostPort.includes("]") || hostPort.split(":").length > 2) {
    return [false, ""];
  }
  let host = hostPort;
  const colon = hostPort.lastIndexOf(":");
  if (colon >= 0) {
    host = hostPort.slice(0, colon);
    if (!validPort(hostPort.slice(colon + 1))) return [false, ""];
  }
  if (!validUriToken(host, URI_UNRESERVED + URI_SUB_DELIMITERS)) return [false, ""];
  return [true, host];
}

function validIpLiteral(value: string): boolean {
  if (value.length >= 4 && "vV".includes(value[0] ?? "")) {
    const dot = value.indexOf(".");
    if (dot < 2) return false;
    const version = value.slice(1, dot);
    const address = value.slice(dot + 1);
    const allowed = URI_UNRESERVED + URI_SUB_DELIMITERS + ":";
    return (
      [...version].every((char) => URI_HEX_DIGITS.includes(char)) &&
      address.length > 0 &&
      [...address].every((char) => allowed.includes(char))
    );
  }
  return validIpv6(value);
}

function validIpv6(value: string): boolean {
  if (value.length === 0 || value.split("::").length > 2) return false;
  if (!value.includes("::")) return ipv6SideGroups(value, true) === 8;
  const [left = "", right = ""] = value.split("::", 2);
  const leftGroups = ipv6SideGroups(left, false);
  const rightGroups = ipv6SideGroups(right, true);
  return leftGroups !== undefined && rightGroups !== undefined && leftGroups + rightGroups < 8;
}

function ipv6SideGroups(value: string, allowIpv4: boolean): number | undefined {
  if (value.length === 0) return 0;
  const parts = value.split(":");
  if (parts.some((part) => part.length === 0)) return undefined;
  let count = 0;
  for (const [index, part] of parts.entries()) {
    if (part.includes(".")) {
      if (!allowIpv4 || index !== parts.length - 1 || !validIpv4(part)) return undefined;
      count += 2;
    } else if (
      part.length > 4 ||
      [...part].some((char) => !URI_HEX_DIGITS.includes(char))
    ) {
      return undefined;
    } else {
      count += 1;
    }
  }
  return count;
}

function validIpv4(value: string): boolean {
  const parts = value.split(".");
  return parts.length === 4 && parts.every((part) =>
    asciiDigits(part) &&
    (part.length === 1 || !part.startsWith("0")) &&
    Number(part) <= 255
  );
}

function asciiAlpha(value: string): boolean {
  return value >= "A" && value <= "Z" || value >= "a" && value <= "z";
}

function asciiDigit(value: string): boolean {
  return value >= "0" && value <= "9";
}

function asciiDigits(value: string): boolean {
  return value.length > 0 && [...value].every(asciiDigit);
}

function validPort(value: string): boolean {
  return value.length === 0 || asciiDigits(value);
}
