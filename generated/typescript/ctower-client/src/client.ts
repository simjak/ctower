// DO NOT EDIT: generated file; regenerate from declared inputs.
// Authored contract digest: sha256:897d0904c0761ce19e89e96d0b2d2b85485582770b37abdcc9765cbdf924e5fb

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

export type AppendCtowerProjectImportCorrectionInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectImportCorrectionRequest;
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

export type BindCtowerProjectAliasPlanInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectAliasPlanBindRequest;
}>;

export type BindCtowerProjectExportEqualityInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectExportEqualityBindRequest;
}>;

export type BootstrapFirstTenantInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly "XCtowerBootstrapCapability": string;
  readonly body: Models.BootstrapRequest;
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

export type CreateCtowerProjectImportRunInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectImportRunCreateRequest;
}>;

export type CreateTicketInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.TicketCreateRequest;
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

export type GetProjectDeliveryInput = Readonly<{
  readonly "projectKey": string;
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

export type IssueSeatCredentialInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.SeatCredentialIssueRequest;
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

export type PlanCompanyBundleInput = Readonly<{
  readonly body: Models.CompanyBundleRequest;
}>;

export type PrepareCtowerProjectCutoverInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectEpochRefusalRequest;
}>;

export type PromoteIntakeEventInput = Readonly<{
  readonly "inboundEventId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.IntakePromotionRequest;
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

export type ReportCtowerProjectFenceObservationInput = Readonly<{
  readonly "IdempotencyKey": string;
  readonly body: Models.CtowerProjectFenceObservationRequest;
}>;

export type ResolveCloseWorkflowInput = Readonly<{
  readonly "ticketId": string;
  readonly "IdempotencyKey": string;
  readonly body: Models.ResolveCloseRequest;
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

export type ValidateCompanyBundleInput = Readonly<{
  readonly body: Models.CompanyBundleRequest;
}>;

export type OperationInputs = Readonly<{
  readonly "addTicketComment": AddTicketCommentInput;
  readonly "addTicketRelation": AddTicketRelationInput;
  readonly "appendCtowerProjectImportCorrection": AppendCtowerProjectImportCorrectionInput;
  readonly "applyCompanyBundle": ApplyCompanyBundleInput;
  readonly "applyCtowerProjectImportBatch": ApplyCtowerProjectImportBatchInput;
  readonly "applyTicketIntent": ApplyTicketIntentInput;
  readonly "bindCtowerProjectAliasPlan": BindCtowerProjectAliasPlanInput;
  readonly "bindCtowerProjectExportEquality": BindCtowerProjectExportEqualityInput;
  readonly "bootstrapFirstTenant": BootstrapFirstTenantInput;
  readonly "changeTicketAssignment": ChangeTicketAssignmentInput;
  readonly "changeTicketPriority": ChangeTicketPriorityInput;
  readonly "commitCtowerProjectDevelopmentEpoch": CommitCtowerProjectDevelopmentEpochInput;
  readonly "createCtowerProjectImportRun": CreateCtowerProjectImportRunInput;
  readonly "createTicket": CreateTicketInput;
  readonly "exportCompanyBundle": ExportCompanyBundleInput;
  readonly "finalizeCtowerProjectImportRun": FinalizeCtowerProjectImportRunInput;
  readonly "freezeProofCriteria": FreezeProofCriteriaInput;
  readonly "getBoard": GetBoardInput;
  readonly "getControlHealth": GetControlHealthInput;
  readonly "getCtowerProjectCutoverHealth": GetCtowerProjectCutoverHealthInput;
  readonly "getCtowerProjectImportRun": GetCtowerProjectImportRunInput;
  readonly "getProjectDelivery": GetProjectDeliveryInput;
  readonly "getSyntheticWorkflowRun": GetSyntheticWorkflowRunInput;
  readonly "getTicket": GetTicketInput;
  readonly "getTicketTimeline": GetTicketTimelineInput;
  readonly "issueSeatCredential": IssueSeatCredentialInput;
  readonly "listTicketAssignments": ListTicketAssignmentsInput;
  readonly "listTicketAuditEvents": ListTicketAuditEventsInput;
  readonly "planCompanyBundle": PlanCompanyBundleInput;
  readonly "prepareCtowerProjectCutover": PrepareCtowerProjectCutoverInput;
  readonly "promoteIntakeEvent": PromoteIntakeEventInput;
  readonly "recordOutboxPoisonDisposition": RecordOutboxPoisonDispositionInput;
  readonly "recordProofEvidence": RecordProofEvidenceInput;
  readonly "recordProofVerdict": RecordProofVerdictInput;
  readonly "reportCtowerProjectFenceObservation": ReportCtowerProjectFenceObservationInput;
  readonly "resolveCloseWorkflow": ResolveCloseWorkflowInput;
  readonly "revokeSeatCredential": RevokeSeatCredentialInput;
  readonly "runSyntheticWorkflow": RunSyntheticWorkflowInput;
  readonly "startTicketWorkflow": StartTicketWorkflowInput;
  readonly "submitIntake": SubmitIntakeInput;
  readonly "transferTicketCustody": TransferTicketCustodyInput;
  readonly "transitionWorkflow": TransitionWorkflowInput;
  readonly "validateCompanyBundle": ValidateCompanyBundleInput;
}>;

export type OperationResults = Readonly<{
  readonly "addTicketComment": Models.TicketCommentResult;
  readonly "addTicketRelation": Models.WorkReceipt;
  readonly "appendCtowerProjectImportCorrection": Models.CtowerProjectMigrationReceipt;
  readonly "applyCompanyBundle": Models.CompanyBundleCommandResult;
  readonly "applyCtowerProjectImportBatch": Models.CtowerProjectImportBatchResult;
  readonly "applyTicketIntent": Models.WorkReceipt;
  readonly "bindCtowerProjectAliasPlan": Models.CtowerProjectImportRun;
  readonly "bindCtowerProjectExportEquality": Models.CtowerProjectImportRun;
  readonly "bootstrapFirstTenant": Models.BootstrapReceipt;
  readonly "changeTicketAssignment": Models.WorkReceipt;
  readonly "changeTicketPriority": Models.WorkReceipt;
  readonly "commitCtowerProjectDevelopmentEpoch": never;
  readonly "createCtowerProjectImportRun": Models.CtowerProjectImportRun;
  readonly "createTicket": Models.TicketCommandResult;
  readonly "exportCompanyBundle": Models.CompanyBundleExportResult;
  readonly "finalizeCtowerProjectImportRun": Models.CtowerProjectReconciliationResult;
  readonly "freezeProofCriteria": Models.ProofReceipt;
  readonly "getBoard": Models.BoardView;
  readonly "getControlHealth": Models.ControlHealth;
  readonly "getCtowerProjectCutoverHealth": Models.CtowerProjectCutoverHealth;
  readonly "getCtowerProjectImportRun": Models.CtowerProjectImportRun;
  readonly "getProjectDelivery": Models.ProjectDeliveryView;
  readonly "getSyntheticWorkflowRun": Models.SyntheticRunResource;
  readonly "getTicket": Models.TicketResource;
  readonly "getTicketTimeline": Models.TimelineResponse;
  readonly "issueSeatCredential": Models.SeatCredentialReceipt;
  readonly "listTicketAssignments": Models.AssignmentList;
  readonly "listTicketAuditEvents": Models.AuditPage;
  readonly "planCompanyBundle": Models.CompanyBundlePlan;
  readonly "prepareCtowerProjectCutover": never;
  readonly "promoteIntakeEvent": Models.IntakeCommandResult;
  readonly "recordOutboxPoisonDisposition": Models.PoisonDispositionReceipt;
  readonly "recordProofEvidence": Models.ProofReceipt;
  readonly "recordProofVerdict": Models.ProofReceipt;
  readonly "reportCtowerProjectFenceObservation": Models.CtowerProjectMigrationReceipt;
  readonly "resolveCloseWorkflow": Models.WorkflowReceipt;
  readonly "revokeSeatCredential": Models.SeatCredentialReceipt;
  readonly "runSyntheticWorkflow": Models.SyntheticRunReceipt;
  readonly "startTicketWorkflow": Models.WorkflowReceipt;
  readonly "submitIntake": Models.IntakeCommandResult;
  readonly "transferTicketCustody": Models.TicketCommandResult;
  readonly "transitionWorkflow": Models.WorkflowReceipt;
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

  public async appendCtowerProjectImportCorrection(
    input: AppendCtowerProjectImportCorrectionInput,
  ): Promise<Models.CtowerProjectMigrationReceipt> {
    return this.execute("appendCtowerProjectImportCorrection", input);
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

  public async bootstrapFirstTenant(
    input: BootstrapFirstTenantInput,
  ): Promise<Models.BootstrapReceipt> {
    return this.execute("bootstrapFirstTenant", input);
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

  public async createCtowerProjectImportRun(
    input: CreateCtowerProjectImportRunInput,
  ): Promise<Models.CtowerProjectImportRun> {
    return this.execute("createCtowerProjectImportRun", input);
  }

  public async createTicket(
    input: CreateTicketInput,
  ): Promise<Models.TicketCommandResult> {
    return this.execute("createTicket", input);
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

  public async getProjectDelivery(
    input: GetProjectDeliveryInput,
  ): Promise<Models.ProjectDeliveryView> {
    return this.execute("getProjectDelivery", input);
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

  public async issueSeatCredential(
    input: IssueSeatCredentialInput,
  ): Promise<Models.SeatCredentialReceipt> {
    return this.execute("issueSeatCredential", input);
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

  public async promoteIntakeEvent(
    input: PromoteIntakeEventInput,
  ): Promise<Models.IntakeCommandResult> {
    return this.execute("promoteIntakeEvent", input);
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
