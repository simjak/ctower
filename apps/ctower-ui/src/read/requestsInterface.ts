import type { Priority } from "@ctower/client";

export type RequestState = "NEW" | "TRIAGED" | "WIP" | "BLOCKED" | "DONE";
export type RequestTriage = "UNTRIAGED" | "ACCEPTED" | "DUPLICATE" | "REJECTED";

/** One accepted Request row, in the order the record returned it. */
export interface RequestEntry {
  readonly requestId: string;
  readonly requestNumber: number;
  readonly reference: string;
  readonly projectKey: string;
  readonly content: string;
  readonly contentSha256: string;
  readonly state: RequestState;
  readonly triage: RequestTriage;
  readonly ownerId: string;
  readonly owner: string;
  readonly priority: Priority;
  readonly priorityDefault: boolean;
  readonly createdAt: string;
  readonly ageSeconds: number;
  readonly requiredTicketIds: readonly string[];
  readonly optionalTicketIds: readonly string[];
  readonly blocker: string | null;
  readonly proofCoverage: number | null;
  readonly durabilityState: "accepted";
  readonly freshness: number;
  readonly sourceKind: string;
  readonly sourceRef: string;
  readonly originalOwnerSha256: string | null;
  readonly decisionBrief: Record<string, unknown> | null;
  readonly unknownReason: string | null;
}

/** The complete accepted-only Request read and its project-answer scope. */
export interface RequestsSnapshot {
  readonly rows: readonly RequestEntry[];
  readonly answeredProjectCount: number;
  readonly answeredProjects: readonly string[];
  readonly observedAt: string;
  readonly requestedProjectCount: number;
  readonly requestedProjects: readonly string[];
  readonly unansweredProjects: readonly string[];
  readonly watermark: number;
}
