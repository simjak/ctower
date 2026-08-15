// DO NOT EDIT: generated file; regenerate from declared inputs.
<<<<<<< HEAD
// Authored contract digest: sha256:4208ed95a16a9bcec349edcf1c8d002f135665367ad1de4131be5b93c46de71e
=======
// Authored contract digest: sha256:b15cd812b396627a264217134e14b9138e5a476ff2652f93594e7c958de52818
>>>>>>> 650210f4 (feat(spawn): publish generated HTTP and CLI surfaces)

import type * as Models from "./models.js";
import { OPERATIONS, type OperationId } from "./operations.js";
import { parseJsonResponse } from "./response-json.js";
import { decodeOperationProblem, decodeOperationResult } from "./validators.js";

export type ClientOptions = Readonly<{
  baseUrl: string;
  credential?: string;
  telemetry: () => Models.TelemetryContext;
  fetch?: typeof globalThis.fetch;
}>;

export type AcknowledgeInboxMessageInput = Readonly<{
  readonly "messageId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.InboxAcknowledgeRequest;
}>;

export type AddKnowledgeDocumentInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.KnowledgeAddRequest;
}>;

export type AddTicketCommentInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.TicketCommentRequest;
}>;

export type AddTicketRelationInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RelationRequest;
}>;

export type AllowConsoleSessionInput = Readonly<{
  readonly body: Models.ConsoleSessionAllowRequest;
}>;

export type AppendAttentionFindingInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.AppendFindingRequest;
}>;

export type AppendCtowerProjectImportCorrectionInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectImportCorrectionRequest;
}>;

export type AppendRequestMaintenanceProposalInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestMaintenanceProposalAppendRequest;
}>;

export type AppendRulingInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.RulingAppendRequest;
}>;

export type AppendSpawnTransitionInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly "spawnId": string;
  readonly body: Models.SpawnTransitionRequest;
}>;

export type ApplyCompanyBundleInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CompanyBundleApplyRequest;
}>;

export type ApplyCtowerProjectImportBatchInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectImportBatchRequest;
}>;

export type ApplyTicketIntentInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.TicketIntentRequest;
}>;

export type ApplyTicketLabelInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.ApplyLabelRequest;
}>;

export type AssignRequestOwnerInput = Readonly<{
  readonly "requestId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestOwnerRequest;
}>;

export type BindCtowerProjectAliasPlanInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectAliasPlanBindRequest;
}>;

export type BindCtowerProjectExportEqualityInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectExportEqualityBindRequest;
}>;

export type BindDreamLaneInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.DreamLaneBindRequest;
}>;

export type BootstrapFirstTenantInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly "XCtowerBootstrapCapability": string;
  readonly body: Models.BootstrapRequest;
}>;

export type CaptureRequestInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestCaptureRequest;
}>;

export type ChangeTicketAssignmentInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.AssignmentChangeRequest;
}>;

export type ChangeTicketPriorityInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.PriorityChangeRequest;
}>;

export type CommitCtowerProjectDevelopmentEpochInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectEpochRefusalRequest;
}>;

export type ConfirmRequestMaintenanceProposalInput = Readonly<{
  readonly "proposalId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestMaintenanceProposalConfirmRequest;
}>;

export type ConsumeDreamDispatchEffectInput = Readonly<{
  readonly "effectId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.DreamDispatchConsumeRequest;
}>;

export type ConsumeReviewDispatchEffectInput = Readonly<{
  readonly "ticketId": string;
  readonly "effectId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.ReviewDispatchConsumeRequest;
}>;

export type CreateCtowerProjectImportRunInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectImportRunCreateRequest;
}>;

export type CreateSpawnRecordInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.SpawnRecordCreateRequest;
}>;

export type CreateTicketInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.TicketCreateRequest;
}>;

export type EvaluateRequestClosureInput = Readonly<{
  readonly "requestId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestClosureEvaluationRequest;
}>;

export type ExportCompanyBundleInput = Readonly<{

}>;

export type FinalizeCtowerProjectImportRunInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectImportFinalizeRequest;
}>;

export type FreezeProofCriteriaInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.FreezeCriteriaRequest;
}>;

export type GetBoardInput = Readonly<{
  readonly "projectKey": string;
  readonly "lane"?: "backlog" | "ready" | "in_progress" | "in_review" | "blocked" | "complete";
  readonly "priority"?: "P0" | "P1" | "P2";
  readonly "stageKey"?: string;
  readonly "custodianId"?: string;
  readonly "assigneeId"?: string;
  readonly "sourceKind"?: string;
  readonly "sourceRef"?: string;
}>;

export type GetControlHealthInput = Readonly<{

}>;

export type GetCtowerProjectCutoverHealthInput = Readonly<{

}>;

export type GetCtowerProjectImportRunInput = Readonly<{
  readonly "runId": string;
}>;

export type GetKnowledgeDocumentInput = Readonly<{
  readonly "documentId": string;
  readonly "scope": "org" | "project";
  readonly "projectKey"?: string;
}>;

export type GetMorningDigestInput = Readonly<{
  readonly "date"?: string;
}>;

export type GetProjectDeliveryInput = Readonly<{
  readonly "projectKey": string;
}>;

export type GetRequestMaintenanceReviewInput = Readonly<{

}>;

export type GetRulingInput = Readonly<{
  readonly "rulingId": string;
}>;

export type GetSpawnRecordInput = Readonly<{
  readonly "spawnId": string;
}>;

export type GetSyntheticWorkflowRunInput = Readonly<{
  readonly "runId": string;
}>;

export type GetTicketInput = Readonly<{
  readonly "ticketId": string;
  readonly "projectKey": string;
}>;

export type GetTicketTimelineInput = Readonly<{
  readonly "ticketId": string;
  readonly "projectKey": string;
}>;

export type IngestInboxNotificationInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.InboxNotificationRequest;
}>;

export type IssueSeatCredentialInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.SeatCredentialIssueRequest;
}>;

export type ListBeatDispatchEffectsInput = Readonly<{

}>;

export type ListBeatRoutinesInput = Readonly<{

}>;

export type ListDreamDispatchEffectsInput = Readonly<{

}>;

export type ListInboxCorrespondentsInput = Readonly<{

}>;

export type ListInboxThreadsInput = Readonly<{
  readonly "unread"?: boolean;
}>;

export type ListKnowledgeDocumentsInput = Readonly<{
  readonly "scope": "org" | "project";
  readonly "projectKey"?: string;
}>;

export type ListProjectEventsInput = Readonly<{
  readonly "projectKey": string;
  readonly "cursor"?: number;
  readonly "limit"?: number;
}>;

export type ListProjectSessionsInput = Readonly<{
  readonly "projectKey": string;
  readonly "cursor"?: number;
  readonly "limit"?: number;
}>;

export type ListRequestMaintenanceProposalsInput = Readonly<{
  readonly "proposalId"?: string;
  readonly "projectKey"?: string;
  readonly "kind"?: "duplicate" | "completed-but-open" | "supersession" | "kill" | "keep";
  readonly "state"?: "OPEN" | "CONFIRMED" | "REJECTED";
}>;

export type ListRequestsInput = Readonly<{
  readonly "projectKey"?: string;
}>;

export type ListReviewDispatchEffectsInput = Readonly<{
  readonly "ticketId": string;
}>;

export type ListRulingsInput = Readonly<{
  readonly "projectKey"?: string;
}>;

export type ListSpawnRecordsInput = Readonly<{
  readonly "projectKey": string;
  readonly "status"?: "requested" | "accepted" | "running" | "completed" | "failed" | "reaped";
  readonly "limit"?: number;
  readonly "offset"?: number;
}>;

export type ListTicketAssignmentsInput = Readonly<{
  readonly "ticketId": string;
  readonly "projectKey": string;
}>;

export type ListTicketAuditEventsInput = Readonly<{
  readonly "ticketId": string;
  readonly "projectKey": string;
  readonly "cursor"?: number;
  readonly "limit"?: number;
}>;

export type ListTicketSessionsInput = Readonly<{
  readonly "ticketId": string;
  readonly "projectKey": string;
}>;

export type PlanCompanyBundleInput = Readonly<{
  readonly body: Models.CompanyBundleRequest;
}>;

export type PrepareCtowerProjectCutoverInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectEpochRefusalRequest;
}>;

export type PrioritizeRequestInput = Readonly<{
  readonly "requestId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestPriorityRequest;
}>;

export type PromoteInboxThreadInput = Readonly<{
  readonly "threadId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.InboxPromotionRequest;
}>;

export type PromoteIntakeEventInput = Readonly<{
  readonly "inboundEventId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.IntakePromotionRequest;
}>;

export type ReadInboxMessageStateInput = Readonly<{
  readonly "threadId": string;
}>;

export type ReadInboxThreadInput = Readonly<{
  readonly "threadId": string;
}>;

export type RecordAttentionFindingDispositionInput = Readonly<{
  readonly "findingId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.FindingDispositionRequest;
}>;

export type RecordOutboxPoisonDispositionInput = Readonly<{
  readonly "outboxId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.PoisonDispositionRequest;
}>;

export type RecordProofEvidenceInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.EvidenceRequest;
}>;

export type RecordProofVerdictInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.VerdictRequest;
}>;

export type RecordTicketChangeReferenceInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.ChangeReferenceRequest;
}>;

export type RecordTicketSessionFactInput = Readonly<{
  readonly "ticketId": string;
  readonly "sessionId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.SessionFactRequest;
}>;

export type RejectRequestMaintenanceProposalInput = Readonly<{
  readonly "proposalId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestMaintenanceProposalRejectRequest;
}>;

export type RelateRequestTicketInput = Readonly<{
  readonly "requestId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestTicketRelationRequest;
}>;

export type ReportCtowerProjectFenceObservationInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectFenceObservationRequest;
}>;

export type ResolveCloseWorkflowInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.ResolveCloseRequest;
}>;

export type RetireBeatRoutineInput = Readonly<{
  readonly "routineRef": string;
  readonly "IdempotencyKey": string;
}>;

export type RevokeSeatCredentialInput = Readonly<{
  readonly "credentialId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.SeatCredentialRevocationRequest;
}>;

export type RunSyntheticWorkflowInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.SyntheticRunRequest;
}>;

export type SendInboxMessageInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.InboxSendRequest;
}>;

export type SetRequestBlockerInput = Readonly<{
  readonly "requestId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestBlockerRequest;
}>;

export type StartTicketSessionInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.SessionStartRequest;
}>;

export type StartTicketWorkflowInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.WorkflowStartRequest;
}>;

export type SubmitIntakeInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.IntakeSubmitRequest;
}>;

export type TransferTicketCustodyInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.CustodyTransferRequest;
}>;

export type TransitionWorkflowInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.WorkflowTransitionRequest;
}>;

export type TriageRequestInput = Readonly<{
  readonly "requestId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.RequestTriageRequest;
}>;

export type ValidateCompanyBundleInput = Readonly<{
  readonly body: Models.CompanyBundleRequest;
}>;

export type OperationInputs = Readonly<{
  readonly "acknowledgeInboxMessage": AcknowledgeInboxMessageInput;
  readonly "addKnowledgeDocument": AddKnowledgeDocumentInput;
  readonly "addTicketComment": AddTicketCommentInput;
  readonly "addTicketRelation": AddTicketRelationInput;
  readonly "allowConsoleSession": AllowConsoleSessionInput;
  readonly "appendAttentionFinding": AppendAttentionFindingInput;
  readonly "appendCtowerProjectImportCorrection": AppendCtowerProjectImportCorrectionInput;
  readonly "appendRequestMaintenanceProposal": AppendRequestMaintenanceProposalInput;
  readonly "appendRuling": AppendRulingInput;
  readonly "appendSpawnTransition": AppendSpawnTransitionInput;
  readonly "applyCompanyBundle": ApplyCompanyBundleInput;
  readonly "applyCtowerProjectImportBatch": ApplyCtowerProjectImportBatchInput;
  readonly "applyTicketIntent": ApplyTicketIntentInput;
  readonly "applyTicketLabel": ApplyTicketLabelInput;
  readonly "assignRequestOwner": AssignRequestOwnerInput;
  readonly "bindCtowerProjectAliasPlan": BindCtowerProjectAliasPlanInput;
  readonly "bindCtowerProjectExportEquality": BindCtowerProjectExportEqualityInput;
  readonly "bindDreamLane": BindDreamLaneInput;
  readonly "bootstrapFirstTenant": BootstrapFirstTenantInput;
  readonly "captureRequest": CaptureRequestInput;
  readonly "changeTicketAssignment": ChangeTicketAssignmentInput;
  readonly "changeTicketPriority": ChangeTicketPriorityInput;
  readonly "commitCtowerProjectDevelopmentEpoch": CommitCtowerProjectDevelopmentEpochInput;
  readonly "confirmRequestMaintenanceProposal": ConfirmRequestMaintenanceProposalInput;
  readonly "consumeDreamDispatchEffect": ConsumeDreamDispatchEffectInput;
  readonly "consumeReviewDispatchEffect": ConsumeReviewDispatchEffectInput;
  readonly "createCtowerProjectImportRun": CreateCtowerProjectImportRunInput;
  readonly "createSpawnRecord": CreateSpawnRecordInput;
  readonly "createTicket": CreateTicketInput;
  readonly "evaluateRequestClosure": EvaluateRequestClosureInput;
  readonly "exportCompanyBundle": ExportCompanyBundleInput;
  readonly "finalizeCtowerProjectImportRun": FinalizeCtowerProjectImportRunInput;
  readonly "freezeProofCriteria": FreezeProofCriteriaInput;
  readonly "getBoard": GetBoardInput;
  readonly "getControlHealth": GetControlHealthInput;
  readonly "getCtowerProjectCutoverHealth": GetCtowerProjectCutoverHealthInput;
  readonly "getCtowerProjectImportRun": GetCtowerProjectImportRunInput;
  readonly "getKnowledgeDocument": GetKnowledgeDocumentInput;
  readonly "getMorningDigest": GetMorningDigestInput;
  readonly "getProjectDelivery": GetProjectDeliveryInput;
  readonly "getRequestMaintenanceReview": GetRequestMaintenanceReviewInput;
  readonly "getRuling": GetRulingInput;
  readonly "getSpawnRecord": GetSpawnRecordInput;
  readonly "getSyntheticWorkflowRun": GetSyntheticWorkflowRunInput;
  readonly "getTicket": GetTicketInput;
  readonly "getTicketTimeline": GetTicketTimelineInput;
  readonly "ingestInboxNotification": IngestInboxNotificationInput;
  readonly "issueSeatCredential": IssueSeatCredentialInput;
  readonly "listBeatDispatchEffects": ListBeatDispatchEffectsInput;
  readonly "listBeatRoutines": ListBeatRoutinesInput;
  readonly "listDreamDispatchEffects": ListDreamDispatchEffectsInput;
  readonly "listInboxCorrespondents": ListInboxCorrespondentsInput;
  readonly "listInboxThreads": ListInboxThreadsInput;
  readonly "listKnowledgeDocuments": ListKnowledgeDocumentsInput;
  readonly "listProjectEvents": ListProjectEventsInput;
  readonly "listProjectSessions": ListProjectSessionsInput;
  readonly "listRequestMaintenanceProposals": ListRequestMaintenanceProposalsInput;
  readonly "listRequests": ListRequestsInput;
  readonly "listReviewDispatchEffects": ListReviewDispatchEffectsInput;
  readonly "listRulings": ListRulingsInput;
  readonly "listSpawnRecords": ListSpawnRecordsInput;
  readonly "listTicketAssignments": ListTicketAssignmentsInput;
  readonly "listTicketAuditEvents": ListTicketAuditEventsInput;
  readonly "listTicketSessions": ListTicketSessionsInput;
  readonly "planCompanyBundle": PlanCompanyBundleInput;
  readonly "prepareCtowerProjectCutover": PrepareCtowerProjectCutoverInput;
  readonly "prioritizeRequest": PrioritizeRequestInput;
  readonly "promoteInboxThread": PromoteInboxThreadInput;
  readonly "promoteIntakeEvent": PromoteIntakeEventInput;
  readonly "readInboxMessageState": ReadInboxMessageStateInput;
  readonly "readInboxThread": ReadInboxThreadInput;
  readonly "recordAttentionFindingDisposition": RecordAttentionFindingDispositionInput;
  readonly "recordOutboxPoisonDisposition": RecordOutboxPoisonDispositionInput;
  readonly "recordProofEvidence": RecordProofEvidenceInput;
  readonly "recordProofVerdict": RecordProofVerdictInput;
  readonly "recordTicketChangeReference": RecordTicketChangeReferenceInput;
  readonly "recordTicketSessionFact": RecordTicketSessionFactInput;
  readonly "rejectRequestMaintenanceProposal": RejectRequestMaintenanceProposalInput;
  readonly "relateRequestTicket": RelateRequestTicketInput;
  readonly "reportCtowerProjectFenceObservation": ReportCtowerProjectFenceObservationInput;
  readonly "resolveCloseWorkflow": ResolveCloseWorkflowInput;
  readonly "retireBeatRoutine": RetireBeatRoutineInput;
  readonly "revokeSeatCredential": RevokeSeatCredentialInput;
  readonly "runSyntheticWorkflow": RunSyntheticWorkflowInput;
  readonly "sendInboxMessage": SendInboxMessageInput;
  readonly "setRequestBlocker": SetRequestBlockerInput;
  readonly "startTicketSession": StartTicketSessionInput;
  readonly "startTicketWorkflow": StartTicketWorkflowInput;
  readonly "submitIntake": SubmitIntakeInput;
  readonly "transferTicketCustody": TransferTicketCustodyInput;
  readonly "transitionWorkflow": TransitionWorkflowInput;
  readonly "triageRequest": TriageRequestInput;
  readonly "validateCompanyBundle": ValidateCompanyBundleInput;
}>;

export type OperationResults = Readonly<{
  readonly "acknowledgeInboxMessage": Models.InboxAcknowledgeResult;
  readonly "addKnowledgeDocument": Models.KnowledgeAddResult;
  readonly "addTicketComment": Models.TicketCommentResult;
  readonly "addTicketRelation": Models.WorkReceipt;
  readonly "allowConsoleSession": Models.ConsoleSessionAllowance;
  readonly "appendAttentionFinding": Models.AttentionFindingResult;
  readonly "appendCtowerProjectImportCorrection": Models.CtowerProjectMigrationReceipt;
  readonly "appendRequestMaintenanceProposal": Models.RequestMaintenanceProposalAppendResult;
  readonly "appendRuling": Models.RulingAppendResult;
  readonly "appendSpawnTransition": Models.SpawnRecordResult;
  readonly "applyCompanyBundle": Models.CompanyBundleCommandResult;
  readonly "applyCtowerProjectImportBatch": Models.CtowerProjectImportBatchResult;
  readonly "applyTicketIntent": Models.WorkReceipt;
  readonly "applyTicketLabel": Models.ApplyLabelResult;
  readonly "assignRequestOwner": Models.RequestChangeResult;
  readonly "bindCtowerProjectAliasPlan": Models.CtowerProjectImportRun;
  readonly "bindCtowerProjectExportEquality": Models.CtowerProjectImportRun;
  readonly "bindDreamLane": Models.DreamLaneBindingReceipt;
  readonly "bootstrapFirstTenant": Models.BootstrapReceipt;
  readonly "captureRequest": Models.RequestCaptureResult;
  readonly "changeTicketAssignment": Models.WorkReceipt;
  readonly "changeTicketPriority": Models.WorkReceipt;
  readonly "commitCtowerProjectDevelopmentEpoch": never;
  readonly "confirmRequestMaintenanceProposal": Models.RequestMaintenanceProposalDecisionResult;
  readonly "consumeDreamDispatchEffect": Models.DreamDispatchReceipt;
  readonly "consumeReviewDispatchEffect": Models.WorkReceipt;
  readonly "createCtowerProjectImportRun": Models.CtowerProjectImportRun;
  readonly "createSpawnRecord": Models.SpawnRecordResult;
  readonly "createTicket": Models.TicketCommandResult;
  readonly "evaluateRequestClosure": Models.RequestChangeResult;
  readonly "exportCompanyBundle": Models.CompanyBundleExportResult;
  readonly "finalizeCtowerProjectImportRun": Models.CtowerProjectReconciliationResult;
  readonly "freezeProofCriteria": Models.ProofReceipt;
  readonly "getBoard": Models.BoardView;
  readonly "getControlHealth": Models.ControlHealth;
  readonly "getCtowerProjectCutoverHealth": Models.CtowerProjectCutoverHealth;
  readonly "getCtowerProjectImportRun": Models.CtowerProjectImportRun;
  readonly "getKnowledgeDocument": Models.KnowledgeDocument;
  readonly "getMorningDigest": Models.MorningDigest;
  readonly "getProjectDelivery": Models.ProjectDeliveryView;
  readonly "getRequestMaintenanceReview": Models.RequestMaintenanceReview;
  readonly "getRuling": Models.RulingRow;
  readonly "getSpawnRecord": Models.SpawnRecordResult;
  readonly "getSyntheticWorkflowRun": Models.SyntheticRunResource;
  readonly "getTicket": Models.TicketResource;
  readonly "getTicketTimeline": Models.TimelineResponse;
  readonly "ingestInboxNotification": Models.InboxSendResult;
  readonly "issueSeatCredential": Models.SeatCredentialReceipt;
  readonly "listBeatDispatchEffects": Models.BeatDispatchEffectList;
  readonly "listBeatRoutines": Models.BeatRoutineList;
  readonly "listDreamDispatchEffects": Models.DreamDispatchEffectList;
  readonly "listInboxCorrespondents": Models.InboxCorrespondentList;
  readonly "listInboxThreads": Models.InboxThreadList;
  readonly "listKnowledgeDocuments": Models.KnowledgeDocumentList;
  readonly "listProjectEvents": Models.ProjectEventPage;
  readonly "listProjectSessions": Models.ProjectSessionPage;
  readonly "listRequestMaintenanceProposals": Models.RequestMaintenanceProposalList;
  readonly "listRequests": Models.RequestList;
  readonly "listReviewDispatchEffects": Models.ReviewDispatchEffectList;
  readonly "listRulings": Models.RulingList;
  readonly "listSpawnRecords": Models.SpawnRecordListResult;
  readonly "listTicketAssignments": Models.AssignmentList;
  readonly "listTicketAuditEvents": Models.AuditPage;
  readonly "listTicketSessions": Models.TicketSessionList;
  readonly "planCompanyBundle": Models.CompanyBundlePlan;
  readonly "prepareCtowerProjectCutover": never;
  readonly "prioritizeRequest": Models.RequestChangeResult;
  readonly "promoteInboxThread": Models.InboxPromotionResult;
  readonly "promoteIntakeEvent": Models.IntakeCommandResult;
  readonly "readInboxMessageState": Models.InboxReadState;
  readonly "readInboxThread": Models.InboxThread;
  readonly "recordAttentionFindingDisposition": Models.FindingDispositionResult;
  readonly "recordOutboxPoisonDisposition": Models.PoisonDispositionReceipt;
  readonly "recordProofEvidence": Models.ProofReceipt;
  readonly "recordProofVerdict": Models.ProofReceipt;
  readonly "recordTicketChangeReference": Models.ChangeReferenceResult;
  readonly "recordTicketSessionFact": Models.SessionReceipt;
  readonly "rejectRequestMaintenanceProposal": Models.RequestMaintenanceProposalDecisionResult;
  readonly "relateRequestTicket": Models.RequestChangeResult;
  readonly "reportCtowerProjectFenceObservation": Models.CtowerProjectMigrationReceipt;
  readonly "resolveCloseWorkflow": Models.WorkflowReceipt;
  readonly "retireBeatRoutine": Models.BeatRoutineRetirementReceipt;
  readonly "revokeSeatCredential": Models.SeatCredentialReceipt;
  readonly "runSyntheticWorkflow": Models.SyntheticRunReceipt;
  readonly "sendInboxMessage": Models.InboxSendResult;
  readonly "setRequestBlocker": Models.RequestChangeResult;
  readonly "startTicketSession": Models.SessionReceipt;
  readonly "startTicketWorkflow": Models.WorkflowReceipt;
  readonly "submitIntake": Models.IntakeCommandResult;
  readonly "transferTicketCustody": Models.TicketCommandResult;
  readonly "transitionWorkflow": Models.WorkflowReceipt;
  readonly "triageRequest": Models.RequestChangeResult;
  readonly "validateCompanyBundle": Models.CompanyBundleValidationResult;
}>;

export class CtowerProblemError extends Error {
  public constructor(public readonly problem: Models.Problem) {
    super(`${problem.code}: ${problem.detail}`);
  }
}

export class CtowerClient {
  readonly #baseUrl: string;
  readonly #credential: string | undefined;
  readonly #telemetry: () => Models.TelemetryContext;
  readonly #fetch: typeof globalThis.fetch;

  public constructor(options: ClientOptions) {
    this.#baseUrl = options.baseUrl;
    this.#credential = options.credential;
    this.#telemetry = options.telemetry;
    this.#fetch = options.fetch ?? globalThis.fetch;
  }

  public async acknowledgeInboxMessage(
    input: AcknowledgeInboxMessageInput,
  ): Promise<Models.InboxAcknowledgeResult> {
    return this.execute("acknowledgeInboxMessage", input);
  }

  public async addKnowledgeDocument(
    input: AddKnowledgeDocumentInput,
  ): Promise<Models.KnowledgeAddResult> {
    return this.execute("addKnowledgeDocument", input);
  }

  public async addTicketComment(
    input: AddTicketCommentInput,
  ): Promise<Models.TicketCommentResult> {
    return this.execute("addTicketComment", input);
  }

  public async addTicketRelation(
    input: AddTicketRelationInput,
  ): Promise<Models.WorkReceipt> {
    return this.execute("addTicketRelation", input);
  }

  public async allowConsoleSession(
    input: AllowConsoleSessionInput,
  ): Promise<Models.ConsoleSessionAllowance> {
    return this.execute("allowConsoleSession", input);
  }

  public async appendAttentionFinding(
    input: AppendAttentionFindingInput,
  ): Promise<Models.AttentionFindingResult> {
    return this.execute("appendAttentionFinding", input);
  }

  public async appendCtowerProjectImportCorrection(
    input: AppendCtowerProjectImportCorrectionInput,
  ): Promise<Models.CtowerProjectMigrationReceipt> {
    return this.execute("appendCtowerProjectImportCorrection", input);
  }

  public async appendRequestMaintenanceProposal(
    input: AppendRequestMaintenanceProposalInput,
  ): Promise<Models.RequestMaintenanceProposalAppendResult> {
    return this.execute("appendRequestMaintenanceProposal", input);
  }

  public async appendRuling(
    input: AppendRulingInput,
  ): Promise<Models.RulingAppendResult> {
    return this.execute("appendRuling", input);
  }

  public async appendSpawnTransition(
    input: AppendSpawnTransitionInput,
  ): Promise<Models.SpawnRecordResult> {
    return this.execute("appendSpawnTransition", input);
  }

  public async applyCompanyBundle(
    input: ApplyCompanyBundleInput,
  ): Promise<Models.CompanyBundleCommandResult> {
    return this.execute("applyCompanyBundle", input);
  }

  public async applyCtowerProjectImportBatch(
    input: ApplyCtowerProjectImportBatchInput,
  ): Promise<Models.CtowerProjectImportBatchResult> {
    return this.execute("applyCtowerProjectImportBatch", input);
  }

  public async applyTicketIntent(
    input: ApplyTicketIntentInput,
  ): Promise<Models.WorkReceipt> {
    return this.execute("applyTicketIntent", input);
  }

  public async applyTicketLabel(
    input: ApplyTicketLabelInput,
  ): Promise<Models.ApplyLabelResult> {
    return this.execute("applyTicketLabel", input);
  }

  public async assignRequestOwner(
    input: AssignRequestOwnerInput,
  ): Promise<Models.RequestChangeResult> {
    return this.execute("assignRequestOwner", input);
  }

  public async bindCtowerProjectAliasPlan(
    input: BindCtowerProjectAliasPlanInput,
  ): Promise<Models.CtowerProjectImportRun> {
    return this.execute("bindCtowerProjectAliasPlan", input);
  }

  public async bindCtowerProjectExportEquality(
    input: BindCtowerProjectExportEqualityInput,
  ): Promise<Models.CtowerProjectImportRun> {
    return this.execute("bindCtowerProjectExportEquality", input);
  }

  public async bindDreamLane(
    input: BindDreamLaneInput,
  ): Promise<Models.DreamLaneBindingReceipt> {
    return this.execute("bindDreamLane", input);
  }

  public async bootstrapFirstTenant(
    input: BootstrapFirstTenantInput,
  ): Promise<Models.BootstrapReceipt> {
    return this.execute("bootstrapFirstTenant", input);
  }

  public async captureRequest(
    input: CaptureRequestInput,
  ): Promise<Models.RequestCaptureResult> {
    return this.execute("captureRequest", input);
  }

  public async changeTicketAssignment(
    input: ChangeTicketAssignmentInput,
  ): Promise<Models.WorkReceipt> {
    return this.execute("changeTicketAssignment", input);
  }

  public async changeTicketPriority(
    input: ChangeTicketPriorityInput,
  ): Promise<Models.WorkReceipt> {
    return this.execute("changeTicketPriority", input);
  }

  public async commitCtowerProjectDevelopmentEpoch(
    input: CommitCtowerProjectDevelopmentEpochInput,
  ): Promise<never> {
    return this.execute("commitCtowerProjectDevelopmentEpoch", input);
  }

  public async confirmRequestMaintenanceProposal(
    input: ConfirmRequestMaintenanceProposalInput,
  ): Promise<Models.RequestMaintenanceProposalDecisionResult> {
    return this.execute("confirmRequestMaintenanceProposal", input);
  }

  public async consumeDreamDispatchEffect(
    input: ConsumeDreamDispatchEffectInput,
  ): Promise<Models.DreamDispatchReceipt> {
    return this.execute("consumeDreamDispatchEffect", input);
  }

  public async consumeReviewDispatchEffect(
    input: ConsumeReviewDispatchEffectInput,
  ): Promise<Models.WorkReceipt> {
    return this.execute("consumeReviewDispatchEffect", input);
  }

  public async createCtowerProjectImportRun(
    input: CreateCtowerProjectImportRunInput,
  ): Promise<Models.CtowerProjectImportRun> {
    return this.execute("createCtowerProjectImportRun", input);
  }

  public async createSpawnRecord(
    input: CreateSpawnRecordInput,
  ): Promise<Models.SpawnRecordResult> {
    return this.execute("createSpawnRecord", input);
  }

  public async createTicket(
    input: CreateTicketInput,
  ): Promise<Models.TicketCommandResult> {
    return this.execute("createTicket", input);
  }

  public async evaluateRequestClosure(
    input: EvaluateRequestClosureInput,
  ): Promise<Models.RequestChangeResult> {
    return this.execute("evaluateRequestClosure", input);
  }

  public async exportCompanyBundle(
    input: ExportCompanyBundleInput,
  ): Promise<Models.CompanyBundleExportResult> {
    return this.execute("exportCompanyBundle", input);
  }

  public async finalizeCtowerProjectImportRun(
    input: FinalizeCtowerProjectImportRunInput,
  ): Promise<Models.CtowerProjectReconciliationResult> {
    return this.execute("finalizeCtowerProjectImportRun", input);
  }

  public async freezeProofCriteria(
    input: FreezeProofCriteriaInput,
  ): Promise<Models.ProofReceipt> {
    return this.execute("freezeProofCriteria", input);
  }

  public async getBoard(
    input: GetBoardInput,
  ): Promise<Models.BoardView> {
    return this.execute("getBoard", input);
  }

  public async getControlHealth(
    input: GetControlHealthInput,
  ): Promise<Models.ControlHealth> {
    return this.execute("getControlHealth", input);
  }

  public async getCtowerProjectCutoverHealth(
    input: GetCtowerProjectCutoverHealthInput,
  ): Promise<Models.CtowerProjectCutoverHealth> {
    return this.execute("getCtowerProjectCutoverHealth", input);
  }

  public async getCtowerProjectImportRun(
    input: GetCtowerProjectImportRunInput,
  ): Promise<Models.CtowerProjectImportRun> {
    return this.execute("getCtowerProjectImportRun", input);
  }

  public async getKnowledgeDocument(
    input: GetKnowledgeDocumentInput,
  ): Promise<Models.KnowledgeDocument> {
    return this.execute("getKnowledgeDocument", input);
  }

  public async getMorningDigest(
    input: GetMorningDigestInput,
  ): Promise<Models.MorningDigest> {
    return this.execute("getMorningDigest", input);
  }

  public async getProjectDelivery(
    input: GetProjectDeliveryInput,
  ): Promise<Models.ProjectDeliveryView> {
    return this.execute("getProjectDelivery", input);
  }

  public async getRequestMaintenanceReview(
    input: GetRequestMaintenanceReviewInput,
  ): Promise<Models.RequestMaintenanceReview> {
    return this.execute("getRequestMaintenanceReview", input);
  }

  public async getRuling(
    input: GetRulingInput,
  ): Promise<Models.RulingRow> {
    return this.execute("getRuling", input);
  }

  public async getSpawnRecord(
    input: GetSpawnRecordInput,
  ): Promise<Models.SpawnRecordResult> {
    return this.execute("getSpawnRecord", input);
  }

  public async getSyntheticWorkflowRun(
    input: GetSyntheticWorkflowRunInput,
  ): Promise<Models.SyntheticRunResource> {
    return this.execute("getSyntheticWorkflowRun", input);
  }

  public async getTicket(
    input: GetTicketInput,
  ): Promise<Models.TicketResource> {
    return this.execute("getTicket", input);
  }

  public async getTicketTimeline(
    input: GetTicketTimelineInput,
  ): Promise<Models.TimelineResponse> {
    return this.execute("getTicketTimeline", input);
  }

  public async ingestInboxNotification(
    input: IngestInboxNotificationInput,
  ): Promise<Models.InboxSendResult> {
    return this.execute("ingestInboxNotification", input);
  }

  public async issueSeatCredential(
    input: IssueSeatCredentialInput,
  ): Promise<Models.SeatCredentialReceipt> {
    return this.execute("issueSeatCredential", input);
  }

  public async listBeatDispatchEffects(
    input: ListBeatDispatchEffectsInput,
  ): Promise<Models.BeatDispatchEffectList> {
    return this.execute("listBeatDispatchEffects", input);
  }

  public async listBeatRoutines(
    input: ListBeatRoutinesInput,
  ): Promise<Models.BeatRoutineList> {
    return this.execute("listBeatRoutines", input);
  }

  public async listDreamDispatchEffects(
    input: ListDreamDispatchEffectsInput,
  ): Promise<Models.DreamDispatchEffectList> {
    return this.execute("listDreamDispatchEffects", input);
  }

  public async listInboxCorrespondents(
    input: ListInboxCorrespondentsInput,
  ): Promise<Models.InboxCorrespondentList> {
    return this.execute("listInboxCorrespondents", input);
  }

  public async listInboxThreads(
    input: ListInboxThreadsInput,
  ): Promise<Models.InboxThreadList> {
    return this.execute("listInboxThreads", input);
  }

  public async listKnowledgeDocuments(
    input: ListKnowledgeDocumentsInput,
  ): Promise<Models.KnowledgeDocumentList> {
    return this.execute("listKnowledgeDocuments", input);
  }

  public async listProjectEvents(
    input: ListProjectEventsInput,
  ): Promise<Models.ProjectEventPage> {
    return this.execute("listProjectEvents", input);
  }

  public async listProjectSessions(
    input: ListProjectSessionsInput,
  ): Promise<Models.ProjectSessionPage> {
    return this.execute("listProjectSessions", input);
  }

  public async listRequestMaintenanceProposals(
    input: ListRequestMaintenanceProposalsInput,
  ): Promise<Models.RequestMaintenanceProposalList> {
    return this.execute("listRequestMaintenanceProposals", input);
  }

  public async listRequests(
    input: ListRequestsInput,
  ): Promise<Models.RequestList> {
    return this.execute("listRequests", input);
  }

  public async listReviewDispatchEffects(
    input: ListReviewDispatchEffectsInput,
  ): Promise<Models.ReviewDispatchEffectList> {
    return this.execute("listReviewDispatchEffects", input);
  }

  public async listRulings(
    input: ListRulingsInput,
  ): Promise<Models.RulingList> {
    return this.execute("listRulings", input);
  }

  public async listSpawnRecords(
    input: ListSpawnRecordsInput,
  ): Promise<Models.SpawnRecordListResult> {
    return this.execute("listSpawnRecords", input);
  }

  public async listTicketAssignments(
    input: ListTicketAssignmentsInput,
  ): Promise<Models.AssignmentList> {
    return this.execute("listTicketAssignments", input);
  }

  public async listTicketAuditEvents(
    input: ListTicketAuditEventsInput,
  ): Promise<Models.AuditPage> {
    return this.execute("listTicketAuditEvents", input);
  }

  public async listTicketSessions(
    input: ListTicketSessionsInput,
  ): Promise<Models.TicketSessionList> {
    return this.execute("listTicketSessions", input);
  }

  public async planCompanyBundle(
    input: PlanCompanyBundleInput,
  ): Promise<Models.CompanyBundlePlan> {
    return this.execute("planCompanyBundle", input);
  }

  public async prepareCtowerProjectCutover(
    input: PrepareCtowerProjectCutoverInput,
  ): Promise<never> {
    return this.execute("prepareCtowerProjectCutover", input);
  }

  public async prioritizeRequest(
    input: PrioritizeRequestInput,
  ): Promise<Models.RequestChangeResult> {
    return this.execute("prioritizeRequest", input);
  }

  public async promoteInboxThread(
    input: PromoteInboxThreadInput,
  ): Promise<Models.InboxPromotionResult> {
    return this.execute("promoteInboxThread", input);
  }

  public async promoteIntakeEvent(
    input: PromoteIntakeEventInput,
  ): Promise<Models.IntakeCommandResult> {
    return this.execute("promoteIntakeEvent", input);
  }

  public async readInboxMessageState(
    input: ReadInboxMessageStateInput,
  ): Promise<Models.InboxReadState> {
    return this.execute("readInboxMessageState", input);
  }

  public async readInboxThread(
    input: ReadInboxThreadInput,
  ): Promise<Models.InboxThread> {
    return this.execute("readInboxThread", input);
  }

  public async recordAttentionFindingDisposition(
    input: RecordAttentionFindingDispositionInput,
  ): Promise<Models.FindingDispositionResult> {
    return this.execute("recordAttentionFindingDisposition", input);
  }

  public async recordOutboxPoisonDisposition(
    input: RecordOutboxPoisonDispositionInput,
  ): Promise<Models.PoisonDispositionReceipt> {
    return this.execute("recordOutboxPoisonDisposition", input);
  }

  public async recordProofEvidence(
    input: RecordProofEvidenceInput,
  ): Promise<Models.ProofReceipt> {
    return this.execute("recordProofEvidence", input);
  }

  public async recordProofVerdict(
    input: RecordProofVerdictInput,
  ): Promise<Models.ProofReceipt> {
    return this.execute("recordProofVerdict", input);
  }

  public async recordTicketChangeReference(
    input: RecordTicketChangeReferenceInput,
  ): Promise<Models.ChangeReferenceResult> {
    return this.execute("recordTicketChangeReference", input);
  }

  public async recordTicketSessionFact(
    input: RecordTicketSessionFactInput,
  ): Promise<Models.SessionReceipt> {
    return this.execute("recordTicketSessionFact", input);
  }

  public async rejectRequestMaintenanceProposal(
    input: RejectRequestMaintenanceProposalInput,
  ): Promise<Models.RequestMaintenanceProposalDecisionResult> {
    return this.execute("rejectRequestMaintenanceProposal", input);
  }

  public async relateRequestTicket(
    input: RelateRequestTicketInput,
  ): Promise<Models.RequestChangeResult> {
    return this.execute("relateRequestTicket", input);
  }

  public async reportCtowerProjectFenceObservation(
    input: ReportCtowerProjectFenceObservationInput,
  ): Promise<Models.CtowerProjectMigrationReceipt> {
    return this.execute("reportCtowerProjectFenceObservation", input);
  }

  public async resolveCloseWorkflow(
    input: ResolveCloseWorkflowInput,
  ): Promise<Models.WorkflowReceipt> {
    return this.execute("resolveCloseWorkflow", input);
  }

  public async retireBeatRoutine(
    input: RetireBeatRoutineInput,
  ): Promise<Models.BeatRoutineRetirementReceipt> {
    return this.execute("retireBeatRoutine", input);
  }

  public async revokeSeatCredential(
    input: RevokeSeatCredentialInput,
  ): Promise<Models.SeatCredentialReceipt> {
    return this.execute("revokeSeatCredential", input);
  }

  public async runSyntheticWorkflow(
    input: RunSyntheticWorkflowInput,
  ): Promise<Models.SyntheticRunReceipt> {
    return this.execute("runSyntheticWorkflow", input);
  }

  public async sendInboxMessage(
    input: SendInboxMessageInput,
  ): Promise<Models.InboxSendResult> {
    return this.execute("sendInboxMessage", input);
  }

  public async setRequestBlocker(
    input: SetRequestBlockerInput,
  ): Promise<Models.RequestChangeResult> {
    return this.execute("setRequestBlocker", input);
  }

  public async startTicketSession(
    input: StartTicketSessionInput,
  ): Promise<Models.SessionReceipt> {
    return this.execute("startTicketSession", input);
  }

  public async startTicketWorkflow(
    input: StartTicketWorkflowInput,
  ): Promise<Models.WorkflowReceipt> {
    return this.execute("startTicketWorkflow", input);
  }

  public async submitIntake(
    input: SubmitIntakeInput,
  ): Promise<Models.IntakeCommandResult> {
    return this.execute("submitIntake", input);
  }

  public async transferTicketCustody(
    input: TransferTicketCustodyInput,
  ): Promise<Models.TicketCommandResult> {
    return this.execute("transferTicketCustody", input);
  }

  public async transitionWorkflow(
    input: TransitionWorkflowInput,
  ): Promise<Models.WorkflowReceipt> {
    return this.execute("transitionWorkflow", input);
  }

  public async triageRequest(
    input: TriageRequestInput,
  ): Promise<Models.RequestChangeResult> {
    return this.execute("triageRequest", input);
  }

  public async validateCompanyBundle(
    input: ValidateCompanyBundleInput,
  ): Promise<Models.CompanyBundleValidationResult> {
    return this.execute("validateCompanyBundle", input);
  }

  private async execute<Id extends OperationId>(
    operationId: Id,
    typedInput: OperationInputs[Id],
  ): Promise<OperationResults[Id]> {
    const operation = OPERATIONS[operationId];
    const input = typedInput as Readonly<Record<string, unknown>>;
    let path = operation.path;
    const headers = new Headers({
      Accept: "application/json",
      "X-Ctower-Telemetry-Context": JSON.stringify(this.#telemetry()),
    });
    if (this.#credential !== undefined) {
      headers.set("Authorization", `Bearer ${this.#credential}`);
    }
    const query = new URLSearchParams();
    for (const parameter of operation.parameters) {
      const value = input[parameter.inputName];
      if (value === undefined || value === null) {
        if (parameter.required) {
          throw new TypeError(`Missing required parameter ${parameter.inputName}`);
        }
        continue;
      }
      if (parameter.location === "path") {
        path = path.replace(`{${parameter.wireName}}`, encodeURIComponent(String(value)));
      } else if (parameter.location === "header") {
        headers.set(parameter.wireName, String(value));
      } else {
        query.set(parameter.wireName, String(value));
      }
    }
    const url = new URL(path, this.#baseUrl);
    url.search = query.toString();
    const body = operation.hasBody ? JSON.stringify(input.body) : undefined;
    if (body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    const response = await this.#fetch(url, {
      method: operation.method,
      headers,
      ...(body === undefined ? {} : { body }),
    });
    const payload = parseJsonResponse(await response.text());
    if (response.status < 200 || response.status > 299) {
      const contentType = response.headers.get("content-type")?.split(";", 1)[0];
      if (contentType !== "application/problem+json") {
        throw new TypeError("ctower returned a non-problem failure");
      }
      const problem = decodeOperationProblem(
        operationId,
        response.status,
        payload,
      ) as Models.Problem;
      throw new CtowerProblemError(problem);
    }
    return decodeOperationResult(
      operationId,
      response.status,
      payload,
    ) as OperationResults[Id];
  }
}
