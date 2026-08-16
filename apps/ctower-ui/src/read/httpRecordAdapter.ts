import { randomBytes, randomUUID } from "node:crypto";
import type {
  AppliedLabel,
  ChangeReference,
  DeliverySurfaceAvailability,
  DurabilityState,
  HumanWaiting,
  Priority,
  ProjectionHealth,
  SurfaceEnvironmentsField,
  SurfaceIdentityField,
  TelemetryContext,
} from "@ctower/client";
import { boundedRead, ReadRefused } from "./bounded";
import { issueReferenceOf } from "./issueRef";
import { reading } from "./outcome";
import { seatNameOf, seatNames } from "./sources/seatNames";
import {
  asArray,
  asBoolean,
  asInteger,
  asIntegerOrNull,
  asMember,
  asRecord,
  asString,
  asStringList,
  asStringOrNull,
  PayloadRefusal,
} from "./json";
import { LANES } from "./interface";
import { defaultProjectKey } from "./projects";
import type {
  BoardCard,
  BoardCards,
  BoardEntry,
  BoardSnapshot,
  InboxCorrespondent,
  InboxCorrespondentChoice,
  InboxCorrespondents,
  InboxDelivery,
  InboxMessageDelivery,
  InboxProjection,
  InboxPromotionPicker,
  InboxThread,
  InboxThreadMessage,
  InboxThreadSummary,
  InstanceIdentity,
  Reading,
  RecordApiReads,
  RecordEvent,
  RecordSource,
  RequestEntry,
  RequestsSnapshot,
  TenantDisplayIdentity,
  TicketRecord,
} from "./interface";

/**
 * The phase-1 implementation: the shadow instance's existing read API.
 *
 * Only GET paths appear here, and every one of them goes through `boundedRead`
 * — this module never calls `fetch` itself. There is no mutation method to call
 * by accident, and the bearer never leaves it: the credential is read from the
 * server process environment and attached to a server-side request, so no
 * browser payload or script on this surface can carry it.
 *
 * The literal unions below are imported as types from the generated client, so
 * a lane, priority, durability or projection-health value this surface accepts
 * cannot drift from the authored contract without a compile failure. The
 * transport is `read/bounded.ts` rather than the generated client's runtime,
 * because that package publishes `./module.js` specifiers over TypeScript
 * sources, which the app bundler does not resolve — and because the generated
 * client issues single-shot requests, which O10 forbids.
 */

const PRIORITIES: readonly Priority[] = ["P0", "P1", "P2"];
const HEALTH: readonly ProjectionHealth[] = ["CURRENT", "STATE_UNKNOWN"];
const DURABILITY: readonly DurabilityState[] = ["durability_pending", "accepted"];
const REQUEST_STATES = ["NEW", "TRIAGED", "WIP", "BLOCKED", "DONE"] as const;
const REQUEST_TRIAGE = ["UNTRIAGED", "ACCEPTED", "DUPLICATE", "REJECTED"] as const;
const REQUEST_DURABILITY = ["accepted"] as const;

function environment(name: string, fallback: string): string {
  const value = process.env[name];
  return value === undefined || value === "" ? fallback : value;
}

export function instanceIdentity(): InstanceIdentity {
  return {
    label: environment("CTOWER_UI_INSTANCE_LABEL", "shadow"),
    posture: environment("CTOWER_UI_INSTANCE_POSTURE", "SHADOW_ONLY_CP3_D_NOT_PROVEN"),
    baseUrl: environment("CTOWER_UI_API_BASE_URL", "http://127.0.0.1:8091"),
  };
}

/**
 * One correlated read context per request. The server binds the authenticated
 * tenant and principal itself, so the values sent here identify the surface,
 * never a claimed identity.
 */
function telemetry(): TelemetryContext {
  const correlation = randomUUID();
  return {
    schema: "ctower.telemetry-context/v1",
    trace_id: randomBytes(16).toString("hex"),
    span_id: randomBytes(8).toString("hex"),
    trace_flags: 0,
    correlation_id: correlation,
    causation_id: correlation,
    command_id: correlation,
    tenant_id: "ctower-ui-read",
    actor_id: "ctower-ui-read",
  };
}

/**
 * One authenticated GET against the instance, under the bounded policy.
 *
 * Exported so a read that belongs to another module — the runtime reads in
 * `runtimeReads.ts` — reaches the instance through this one request shape
 * rather than assembling its own headers, and so the credential is still read
 * in exactly one place.
 */
export async function read(path: string): Promise<unknown> {
  const credential = process.env.CTOWER_UI_API_TOKEN;
  if (credential === undefined || credential === "") {
    throw new ReadRefused({
      reason: "no read credential is configured; set CTOWER_UI_API_TOKEN from the instance keyring",
      failureClass: "permanent",
      attempts: 0,
      elapsedMs: 0,
      // the API was never asked, so there is no status to report
      status: null,
    });
  }
  return await boundedRead(`${instanceIdentity().baseUrl}${path}`, {
    Accept: "application/json",
    Authorization: `Bearer ${credential}`,
    "X-Ctower-Telemetry-Context": JSON.stringify(telemetry()),
  });
}

function optionalText(value: unknown, field: string): string | null {
  const text = asStringOrNull(value, field);
  return text === null || text === "None" ? null : text;
}

const TENANT_DISPLAY_STATES = ["known", "unknown"] as const;

function toTenantDisplayIdentity(value: unknown): TenantDisplayIdentity {
  const row = asRecord(value, "board.card.tenant_display_identity");
  const state = asMember(
    row.state,
    "board.card.tenant_display_identity.state",
    TENANT_DISPLAY_STATES
  );
  return state === "known"
    ? {
        state,
        displayName: asString(row.display_name, "board.card.tenant_display_identity.display_name"),
      }
    : {
        state,
        missingSource: asString(
          row.missing_source,
          "board.card.tenant_display_identity.missing_source"
        ),
      };
}

function toChangeReference(value: unknown): ChangeReference {
  const row = asRecord(value, "board.card.change_references[]");
  return {
    repository: asString(row.repository, "board.card.change_references[].repository"),
    change_identity: asString(
      row.change_identity,
      "board.card.change_references[].change_identity"
    ),
    reference: asString(row.reference, "board.card.change_references[].reference"),
    recorded_at: asString(row.recorded_at, "board.card.change_references[].recorded_at"),
  };
}

function toAppliedLabel(value: unknown): AppliedLabel {
  const row = asRecord(value, "board.card.applied_labels[]");
  return {
    label_key: asString(row.label_key, "board.card.applied_labels[].label_key"),
    label: asString(row.label, "board.card.applied_labels[].label"),
    vocabulary_revision: asInteger(
      row.vocabulary_revision,
      "board.card.applied_labels[].vocabulary_revision"
    ),
    applied_at: asString(row.applied_at, "board.card.applied_labels[].applied_at"),
  };
}

const HUMAN_WAITING_STATES = ["waiting", "not_waiting"] as const;

function toHumanWaiting(value: unknown): HumanWaiting {
  const row = asRecord(value, "board.card.human_waiting");
  const state = asMember(row.state, "board.card.human_waiting.state", HUMAN_WAITING_STATES);
  return state === "waiting"
    ? {
        state,
        finding_id: asString(row.finding_id, "board.card.human_waiting.finding_id"),
        kind_key: asString(row.kind_key, "board.card.human_waiting.kind_key"),
        reason_code: asString(row.reason_code, "board.card.human_waiting.reason_code"),
      }
    : { state };
}

const SURFACE_DECLARATION_STATES = ["declared_present", "declared_absent", "undeclared"] as const;

function toSurfaceIdentity(value: unknown, field: string): SurfaceIdentityField {
  const row = asRecord(value, field);
  return {
    state: asMember(row.state, `${field}.state`, SURFACE_DECLARATION_STATES),
    identity: asStringOrNull(row.identity, `${field}.identity`),
  };
}

function toSurfaceEnvironments(value: unknown, field: string): SurfaceEnvironmentsField {
  const row = asRecord(value, field);
  return {
    state: asMember(row.state, `${field}.state`, SURFACE_DECLARATION_STATES),
    environments: asStringList(row.environments, `${field}.environments`),
  };
}

const DELIVERY_SURFACE_STATES = ["no_qualifying_checkpoint", "qualifying_checkpoint"] as const;

function requiredStringOrNull(
  row: Readonly<Record<string, unknown>>,
  property: string,
  field: string
): string | null {
  if (!Object.hasOwn(row, property)) {
    throw new PayloadRefusal(field, "a string or null");
  }
  return asStringOrNull(row[property], field);
}

function toDeliverySurfaceAvailability(value: unknown): DeliverySurfaceAvailability {
  const field = "board.card.delivery_surface_availability";
  const row = asRecord(value, field);
  const state = asMember(row.state, `${field}.state`, DELIVERY_SURFACE_STATES);
  return state === "no_qualifying_checkpoint"
    ? { state }
    : {
        state,
        checkpoint_key: asString(row.checkpoint_key, `${field}.checkpoint_key`),
        landing_boundary: toSurfaceIdentity(row.landing_boundary, `${field}.landing_boundary`),
        non_production_environments: toSurfaceEnvironments(
          row.non_production_environments,
          `${field}.non_production_environments`
        ),
        externally_effective_outcome: toSurfaceIdentity(
          row.externally_effective_outcome,
          `${field}.externally_effective_outcome`
        ),
      };
}

function toCard(value: unknown, names: Readonly<Record<string, string>>): BoardCard {
  const row = asRecord(value, "board.card");
  return {
    ticketId: asString(row.ticket_id, "board.card.ticket_id"),
    projectKey: asString(row.project_key, "board.card.project_key"),
    title: asString(row.title, "board.card.title"),
    lane: asMember(row.lane, "board.card.lane", LANES),
    priority: asMember(row.priority, "board.card.priority", PRIORITIES),
    stageKey: optionalText(row.stage_key, "board.card.stage_key"),
    stageLabel: optionalText(row.stage_label, "board.card.stage_label"),
    activityClass: optionalText(row.activity_class, "board.card.activity_class"),
    custodianId: asString(row.custodian_id, "board.card.custodian_id"),
    custodianName: seatNameOf(names, asString(row.custodian_id, "board.card.custodian_id")),
    assigneeId: asStringOrNull(row.assignee_id, "board.card.assignee_id"),
    assigneeName: seatNameOf(
      names,
      asStringOrNull(row.assignee_id, "board.card.assignee_id") ?? ""
    ),
    blockerReason: asStringOrNull(row.blocker_reason, "board.card.blocker_reason"),
    blockerOpenedAt: asStringOrNull(row.blocker_opened_at, "board.card.blocker_opened_at"),
    risk: optionalText(row.risk, "board.card.risk"),
    deliveryFacts: asStringList(row.delivery_facts ?? [], "board.card.delivery_facts"),
    inboxThreadIds: asStringList(row.inbox_thread_ids, "board.card.inbox_thread_ids"),
    tenantDisplayIdentity: toTenantDisplayIdentity(row.tenant_display_identity),
    changeReferences: asArray(row.change_references, "board.card.change_references").map(
      toChangeReference
    ),
    appliedLabels: asArray(row.applied_labels, "board.card.applied_labels").map(toAppliedLabel),
    humanWaiting: toHumanWaiting(row.human_waiting),
    deliverySurfaceAvailability: toDeliverySurfaceAvailability(row.delivery_surface_availability),
    version: asInteger(row.version, "board.card.version"),
  };
}

function toRequestEntry(value: unknown): RequestEntry {
  const row = asRecord(value, "requests.rows[]");
  return {
    requestId: asString(row.request_id, "requests.rows[].request_id"),
    requestNumber: asInteger(row.request_number, "requests.rows[].request_number"),
    reference: asString(row.reference, "requests.rows[].reference"),
    projectKey: asString(row.project_key, "requests.rows[].project_key"),
    content: asString(row.content, "requests.rows[].content"),
    contentSha256: asString(row.content_sha256, "requests.rows[].content_sha256"),
    state: asMember(row.state, "requests.rows[].state", REQUEST_STATES),
    triage: asMember(row.triage, "requests.rows[].triage", REQUEST_TRIAGE),
    ownerId: asString(row.owner_id, "requests.rows[].owner_id"),
    owner: asString(row.owner, "requests.rows[].owner"),
    priority: asMember(row.priority, "requests.rows[].priority", PRIORITIES),
    priorityDefault: asBoolean(row.priority_default, "requests.rows[].priority_default"),
    createdAt: asString(row.created_at, "requests.rows[].created_at"),
    ageSeconds: asInteger(row.age_seconds, "requests.rows[].age_seconds"),
    requiredTicketIds: asStringList(row.required_ticket_ids, "requests.rows[].required_ticket_ids"),
    optionalTicketIds: asStringList(row.optional_ticket_ids, "requests.rows[].optional_ticket_ids"),
    blocker: asStringOrNull(row.blocker, "requests.rows[].blocker"),
    proofCoverage: asIntegerOrNull(row.proof_coverage, "requests.rows[].proof_coverage"),
    durabilityState: asMember(
      row.durability_state,
      "requests.rows[].durability_state",
      REQUEST_DURABILITY
    ),
    freshness: asInteger(row.freshness, "requests.rows[].freshness"),
    sourceKind: asString(row.source_kind, "requests.rows[].source_kind"),
    sourceRef: asString(row.source_ref, "requests.rows[].source_ref"),
    originalOwnerSha256: asStringOrNull(
      row.original_owner_sha256,
      "requests.rows[].original_owner_sha256"
    ),
    decisionBrief:
      row.decision_brief === null
        ? null
        : asRecord(row.decision_brief, "requests.rows[].decision_brief"),
    unknownReason: asStringOrNull(row.unknown_reason, "requests.rows[].unknown_reason"),
  };
}

/** Parse the complete accepted-only Request list without inventing defaults. */
export function requestsFrom(value: unknown): RequestsSnapshot {
  const row = asRecord(value, "requests");
  return {
    rows: asArray(row.rows, "requests.rows").map(toRequestEntry),
    answeredProjectCount: asInteger(row.answered_project_count, "requests.answered_project_count"),
    answeredProjects: asStringList(row.answered_projects, "requests.answered_projects"),
    observedAt: asString(row.observed_at, "requests.observed_at"),
    requestedProjectCount: asInteger(
      row.requested_project_count,
      "requests.requested_project_count"
    ),
    requestedProjects: asStringList(row.requested_projects, "requests.requested_projects"),
    unansweredProjects: asStringList(row.unanswered_projects, "requests.unanswered_projects"),
    watermark: asInteger(row.watermark, "requests.watermark"),
  };
}

/** The recorded source, plus the issue it addresses when the record names one. */
function sourceOf(kind: string, ref: string): RecordSource {
  return { kind, ref, issue: issueReferenceOf(kind, ref) };
}

function toTicket(value: unknown, names: Readonly<Record<string, string>>): TicketRecord {
  const row = asRecord(value, "ticket");
  const source = asRecord(row.source, "ticket.source");
  return {
    ticketId: asString(row.ticket_id, "ticket.ticket_id"),
    title: asString(row.title, "ticket.title"),
    priority: asMember(row.priority, "ticket.priority", PRIORITIES),
    custodianId: asString(row.custodian_id, "ticket.custodian_id"),
    custodianName: seatNameOf(names, asString(row.custodian_id, "ticket.custodian_id")),
    createdAt: asString(row.created_at, "ticket.created_at"),
    durabilityState: asMember(row.durability_state, "ticket.durability_state", DURABILITY),
    version: asInteger(row.version, "ticket.version"),
    source: sourceOf(
      asString(source.kind, "ticket.source.kind"),
      asString(source.ref, "ticket.source.ref")
    ),
  };
}

function toEvent(value: unknown): RecordEvent {
  const row = asRecord(value, "audit.event");
  return {
    eventId: asString(row.event_id, "audit.event.event_id"),
    sequence: asInteger(row.sequence, "audit.event.sequence"),
    kind: asString(row.kind, "audit.event.kind"),
    occurredAt: asString(row.occurred_at, "audit.event.occurred_at"),
    actorPrincipalId: asString(row.actor_principal_id, "audit.event.actor_principal_id"),
    commandId: asString(row.command_id, "audit.event.command_id"),
    streamId: asStringOrNull(row.stream_id, "audit.event.stream_id"),
    eventHash: asStringOrNull(row.event_hash, "audit.event.event_hash"),
    recordPosition: asIntegerOrNull(row.record_position, "audit.event.record_position"),
    payload: asRecord(row.payload ?? {}, "audit.event.payload"),
  };
}

function toInboxThreadSummary(value: unknown): InboxThreadSummary {
  const row = asRecord(value, "inbox.threads[]");
  return {
    threadId: asString(row.thread_id, "inbox.threads[].thread_id"),
    otherAgent: asString(row.other_agent, "inbox.threads[].other_agent"),
    lastMessagePreview: asString(row.last_message_preview, "inbox.threads[].last_message_preview"),
    lastMessageAt: asString(row.last_message_at, "inbox.threads[].last_message_at"),
    unreadCount: asInteger(row.unread_count, "inbox.threads[].unread_count"),
    promotedTicketId: requiredStringOrNull(
      row,
      "promoted_ticket_id",
      "inbox.threads[].promoted_ticket_id"
    ),
  };
}

function toInboxMessage(value: unknown): InboxThreadMessage {
  const row = asRecord(value, "inbox.thread.messages[]");
  return {
    messageId: asString(row.message_id, "inbox.thread.messages[].message_id"),
    position: asInteger(row.position, "inbox.thread.messages[].position"),
    from: asString(row.from, "inbox.thread.messages[].from"),
    to: asString(row.to, "inbox.thread.messages[].to"),
    text: asString(row.text, "inbox.thread.messages[].text"),
    sentAt: asString(row.sent_at, "inbox.thread.messages[].sent_at"),
  };
}

export function inboxProjectionFrom(value: unknown): InboxProjection {
  const row = asRecord(value, "inbox");
  return {
    recipient: asString(row.recipient, "inbox.recipient"),
    threads: asArray(row.threads, "inbox.threads").map(toInboxThreadSummary),
    totalUnread: asInteger(row.total_unread, "inbox.total_unread"),
    unreadOnly: asBoolean(row.unread_only, "inbox.unread_only"),
  };
}

export function inboxThreadFrom(value: unknown): InboxThread {
  const row = asRecord(value, "inbox.thread");
  return {
    threadId: asString(row.thread_id, "inbox.thread.thread_id"),
    participants: asStringList(row.participants, "inbox.thread.participants"),
    messages: asArray(row.messages, "inbox.thread.messages").map(toInboxMessage),
    readThroughPosition: asInteger(row.read_through_position, "inbox.thread.read_through_position"),
    promotedTicketId: requiredStringOrNull(
      row,
      "promoted_ticket_id",
      "inbox.thread.promoted_ticket_id"
    ),
  };
}

/** `project_key` is a required query parameter on every one of these paths. */
function scoped(path: string, projectKey: string): string {
  return `${path}?project_key=${encodeURIComponent(projectKey)}`;
}

async function loadRequests(projectKey: string | null): Promise<RequestsSnapshot> {
  return requestsFrom(
    await read(projectKey === null ? "/v1/requests" : scoped("/v1/requests", projectKey))
  );
}

async function loadTicket(ticketId: string, projectKey: string): Promise<TicketRecord> {
  const names = await seatNames();
  return toTicket(
    await read(scoped(`/v1/tickets/${encodeURIComponent(ticketId)}`, projectKey)),
    names
  );
}

/** The cards for one project, with every returned card checked against it. */
async function loadBoardCards(projectKey: string): Promise<BoardCards> {
  const view = asRecord(await read(scoped("/v1/board", projectKey)), "board");
  const names = await seatNames();
  const cards = asArray(view.cards, "board.cards").map((card) => toCard(card, names));
  const foreignCard = cards.find((card) => card.projectKey !== projectKey);
  if (foreignCard !== undefined) {
    throw new TypeError(
      `board.card.project_key was ${foreignCard.projectKey}; scoped read asked for ${projectKey}`
    );
  }
  return {
    cards,
    health: asMember(view.health, "board.health", HEALTH),
    projectionWatermark: asInteger(view.projection_watermark, "board.projection_watermark"),
    sourceWatermark: asInteger(view.source_watermark, "board.source_watermark"),
    scope: { projectKey },
  };
}

/** The board for one project, each card joined to the ticket read behind it. */
async function loadBoard(projectKey: string): Promise<BoardSnapshot> {
  const { cards, ...view } = await loadBoardCards(projectKey);
  const entries: readonly BoardEntry[] = await Promise.all(
    cards.map(async (card): Promise<BoardEntry> => ({
      card,
      // the per-card join keeps its own reading: a card whose ticket read failed
      // must say so, not silently lose its source and its age
      ticket: await reading(async () => await loadTicket(card.ticketId, projectKey)),
    }))
  );
  return { ...view, entries };
}

async function loadAudit(ticketId: string, projectKey: string): Promise<readonly RecordEvent[]> {
  const view = asRecord(
    await read(scoped(`/v1/tickets/${encodeURIComponent(ticketId)}/audit`, projectKey)),
    "audit"
  );
  return asArray(view.events, "audit.events").map(toEvent);
}

async function loadInbox(): Promise<InboxProjection> {
  return inboxProjectionFrom(await read("/v1/inbox/threads"));
}

async function loadInboxThread(threadId: string): Promise<InboxThread> {
  return inboxThreadFrom(await read(`/v1/inbox/threads/${encodeURIComponent(threadId)}`));
}

const DELIVERY_STATES = ["sent", "delivered", "read"] as const;

function toMessageDelivery(value: unknown): InboxMessageDelivery {
  const row = asRecord(value, "inbox.read-state.messages[]");
  return {
    messageId: asString(row.message_id, "inbox.read-state.messages[].message_id"),
    position: asInteger(row.position, "inbox.read-state.messages[].position"),
    recipient: asString(row.recipient, "inbox.read-state.messages[].recipient"),
    state: asMember(row.state, "inbox.read-state.messages[].state", DELIVERY_STATES),
    deliveredAt: asStringOrNull(row.delivered_at, "inbox.read-state.messages[].delivered_at"),
    readAt: asStringOrNull(row.read_at, "inbox.read-state.messages[].read_at"),
  };
}

/**
 * One thread's append-only delivery truth, keyed by message.
 *
 * The approved chat surface draws a sent/delivered/read mark on every message,
 * and those are three *recorded* facts with their own event ids — not something
 * derivable from the thread read's own cursor. So this is a second request
 * beside the thread, kept as its own reading: a transcript whose delivery read
 * did not answer draws no marks and says so, rather than drawing every message
 * as merely sent, which would be a claim the record never made.
 */
export async function loadInboxDelivery(threadId: string): Promise<InboxDelivery> {
  const row = asRecord(
    await read(`/v1/inbox/threads/${encodeURIComponent(threadId)}/read-state`),
    "inbox.read-state"
  );
  const messages = asArray(row.messages, "inbox.read-state.messages").map(toMessageDelivery);
  return new Map(messages.map((message) => [message.messageId, message]));
}

/**
 * The two seats one thread is between, taken from the server's own answer.
 *
 * The projection is recipient-scoped: it names the authenticated principal's
 * seat once and the other participant per thread, so neither identity is
 * inferred here from a participant list or accepted from a browser. A thread
 * this principal is not a participant of is absent from the projection and
 * refuses by name rather than resolving to a guess.
 */
export async function loadInboxCorrespondent(threadId: string): Promise<InboxCorrespondent> {
  const projection = await loadInbox();
  const summary = projection.threads.find((thread) => thread.threadId === threadId);
  if (summary === undefined) {
    throw new PayloadRefusal("inbox.threads", "a thread this principal participates in");
  }
  return { sender: projection.recipient, recipient: summary.otherAgent };
}

function toCorrespondentChoice(value: unknown): InboxCorrespondentChoice {
  const row = asRecord(value, "inbox.correspondents[]");
  return {
    seatKey: asString(row.seat_key, "inbox.correspondents[].seat_key"),
    projectKey: asString(row.project_key, "inbox.correspondents[].project_key"),
  };
}

/**
 * The seats a new thread may be opened to, exactly as the record lists them.
 *
 * Nothing here filters, sorts or supplements that list. A picker that added a
 * name the record does not hold would offer an address the command refuses, and
 * one that dropped a name the record does hold would hide a correspondent the
 * operator is entitled to write to — either way the surface would be answering
 * a question only the record can answer.
 */
export async function loadInboxCorrespondents(): Promise<InboxCorrespondents> {
  const row = asRecord(await read("/v1/inbox/correspondents"), "inbox.correspondents");
  return {
    sender: asString(row.sender, "inbox.correspondents.sender"),
    choices: asArray(row.correspondents, "inbox.correspondents.correspondents").map(
      toCorrespondentChoice
    ),
  };
}

/**
 * The target picker uses the same project-scoped Board record as the Board
 * screen. A failed read remains visible to the user, while creating a ticket
 * from the thread stays available because that operation needs no target.
 */
async function loadInboxPromotionPicker(): Promise<InboxPromotionPicker> {
  try {
    const snapshot = await loadBoard(defaultProjectKey());
    return {
      choices: snapshot.entries.map(({ card }) => ({
        ticketId: card.ticketId,
        projectKey: card.projectKey,
        title: card.title,
      })),
      notice: null,
    };
  } catch {
    return {
      choices: [],
      notice:
        "Existing ticket choices could not be loaded. You can still create a new ticket from this thread.",
    };
  }
}

export const httpRecordAdapter: RecordApiReads = {
  instance: instanceIdentity(),
  board: async (projectKey: string): Promise<Reading<BoardSnapshot>> =>
    await reading(async () => await loadBoard(projectKey)),
  boardCards: async (projectKey: string): Promise<Reading<BoardCards>> =>
    await reading(async () => await loadBoardCards(projectKey)),
  requests: async (projectKey: string | null): Promise<Reading<RequestsSnapshot>> =>
    await reading(async () => await loadRequests(projectKey)),
  ticket: async (ticketId: string, projectKey: string): Promise<Reading<TicketRecord>> =>
    await reading(async () => await loadTicket(ticketId, projectKey)),
  ticketAudit: async (
    ticketId: string,
    projectKey: string
  ): Promise<Reading<readonly RecordEvent[]>> =>
    await reading(async () => await loadAudit(ticketId, projectKey)),
  inbox: async (): Promise<Reading<InboxProjection>> => await reading(loadInbox),
  inboxThread: async (threadId: string): Promise<Reading<InboxThread>> =>
    await reading(async () => await loadInboxThread(threadId)),
  inboxDelivery: async (threadId: string): Promise<Reading<InboxDelivery>> =>
    await reading(async () => await loadInboxDelivery(threadId)),
  inboxCorrespondent: async (threadId: string): Promise<Reading<InboxCorrespondent>> =>
    await reading(async () => await loadInboxCorrespondent(threadId)),
  inboxCorrespondents: async (): Promise<Reading<InboxCorrespondents>> =>
    await reading(loadInboxCorrespondents),
  inboxPromotionPicker: loadInboxPromotionPicker,
};
