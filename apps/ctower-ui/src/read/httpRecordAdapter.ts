import { randomBytes, randomUUID } from "node:crypto";
import type { DurabilityState, Priority, ProjectionHealth, TelemetryContext } from "@ctower/client";
import { boundedRead, ReadRefused } from "./bounded";
import { NO_WORK_SESSIONS } from "./futureSources";
import { issueReferenceOf } from "./issueRef";
import { reading } from "./outcome";
import { seatNameOf, seatNames } from "./sources/seatNames";
import {
  asArray,
  asInteger,
  asIntegerOrNull,
  asMember,
  asRecord,
  asString,
  asStringList,
  asStringOrNull,
} from "./json";
import { LANES } from "./interface";
import type {
  BoardCard,
  BoardEntry,
  BoardSnapshot,
  InstanceIdentity,
  Reading,
  RecordApiReads,
  RecordEvent,
  RecordSource,
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

async function read(path: string): Promise<unknown> {
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

function toCard(value: unknown, names: Readonly<Record<string, string>>): BoardCard {
  const row = asRecord(value, "board.card");
  return {
    ticketId: asString(row.ticket_id, "board.card.ticket_id"),
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
    version: asInteger(row.version, "board.card.version"),
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

/** `project_key` is a required query parameter on every one of these paths. */
function scoped(path: string, projectKey: string): string {
  return `${path}?project_key=${encodeURIComponent(projectKey)}`;
}

async function loadTicket(ticketId: string, projectKey: string): Promise<TicketRecord> {
  const names = await seatNames();
  return toTicket(
    await read(scoped(`/v1/tickets/${encodeURIComponent(ticketId)}`, projectKey)),
    names
  );
}

/**
 * The board for one project.
 *
 * The read is scoped — `project_key` is required by the contract — but the cards
 * that come back carry no project member, so this reports `cardsCarryProject:
 * false` and the screen says what that means rather than letting three tabs
 * imply three different boards. That flag is derived from the card shape this
 * module parses, not from a probe of today's behaviour: it flips when the record
 * starts carrying the fact, and the screen changes with it.
 */
async function loadBoard(projectKey: string): Promise<BoardSnapshot> {
  const view = asRecord(await read(scoped("/v1/board", projectKey)), "board");
  const names = await seatNames();
  const cards = asArray(view.cards, "board.cards").map((card) => toCard(card, names));
  const entries: readonly BoardEntry[] = await Promise.all(
    cards.map(async (card): Promise<BoardEntry> => ({
      card,
      // the per-card join keeps its own reading: a card whose ticket read failed
      // must say so, not silently lose its source and its age
      ticket: await reading(async () => await loadTicket(card.ticketId, projectKey)),
    }))
  );
  return {
    entries,
    health: asMember(view.health, "board.health", HEALTH),
    projectionWatermark: asInteger(view.projection_watermark, "board.projection_watermark"),
    sourceWatermark: asInteger(view.source_watermark, "board.source_watermark"),
    scope: { projectKey, cardsCarryProject: CARD_CARRIES_PROJECT },
  };
}

/**
 * Whether the parsed Board card carries a project of its own.
 *
 * `toCard` above is the whole of what this surface reads from a card, and no
 * member of it is a project. When the contract adds one, `toCard` gains the
 * field and this becomes true in the same edit — the two cannot drift.
 */
const CARD_CARRIES_PROJECT = false;

async function loadAudit(ticketId: string, projectKey: string): Promise<readonly RecordEvent[]> {
  const view = asRecord(
    await read(scoped(`/v1/tickets/${encodeURIComponent(ticketId)}/audit`, projectKey)),
    "audit"
  );
  return asArray(view.events, "audit.events").map(toEvent);
}

export const httpRecordAdapter: RecordApiReads = {
  instance: instanceIdentity(),
  board: async (projectKey: string): Promise<Reading<BoardSnapshot>> =>
    await reading(async () => await loadBoard(projectKey)),
  ticket: async (ticketId: string, projectKey: string): Promise<Reading<TicketRecord>> =>
    await reading(async () => await loadTicket(ticketId, projectKey)),
  ticketAudit: async (
    ticketId: string,
    projectKey: string
  ): Promise<Reading<readonly RecordEvent[]>> =>
    await reading(async () => await loadAudit(ticketId, projectKey)),
  workSessions: (): Promise<Reading<never>> =>
    Promise.resolve({ state: "absent", source: NO_WORK_SESSIONS }),
};
