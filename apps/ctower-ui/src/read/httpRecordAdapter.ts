import { randomBytes, randomUUID } from "node:crypto";
import type { DurabilityState, Priority, ProjectionHealth, TelemetryContext } from "@ctower/client";
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
  RecordAdapter,
  Reading,
  RecordEvent,
  TicketRecord,
} from "./interface";

/**
 * The phase-1 implementation: the shadow instance's existing read API.
 *
 * Only GET paths appear here. There is no mutation method in this module to
 * call by accident, and the bearer never leaves it — the credential is read
 * from the server process environment and attached to a server-side request,
 * so no browser payload, script, or URL on this surface can carry it.
 *
 * The literal unions below are imported as types from the generated client, so
 * a lane, priority, durability or projection-health value this surface accepts
 * cannot drift from the authored contract without a compile failure. The
 * request itself is a plain `fetch` rather than the generated client's runtime,
 * because that package publishes `./module.js` specifiers over TypeScript
 * sources, which the app bundler does not resolve.
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
    throw new Error(
      "no read credential is configured; set CTOWER_UI_API_TOKEN from the instance keyring"
    );
  }
  const response = await fetch(`${instanceIdentity().baseUrl}${path}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${credential}`,
      "X-Ctower-Telemetry-Context": JSON.stringify(telemetry()),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`the read API answered ${response.status.toString()} for ${path}`);
  }
  return await response.json();
}

function refusalText(error: unknown): string {
  return error instanceof Error ? error.message : "the read did not complete";
}

async function reading<T>(load: () => Promise<T>): Promise<Reading<T>> {
  try {
    return { state: "present", value: await load() };
  } catch (error: unknown) {
    return { state: "unavailable", reason: refusalText(error) };
  }
}

function optionalText(value: unknown, field: string): string | null {
  const text = asStringOrNull(value, field);
  return text === null || text === "None" ? null : text;
}

function toCard(value: unknown): BoardCard {
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
    assigneeId: asStringOrNull(row.assignee_id, "board.card.assignee_id"),
    blockerReason: asStringOrNull(row.blocker_reason, "board.card.blocker_reason"),
    blockerOpenedAt: asStringOrNull(row.blocker_opened_at, "board.card.blocker_opened_at"),
    risk: optionalText(row.risk, "board.card.risk"),
    deliveryFacts: asStringList(row.delivery_facts ?? [], "board.card.delivery_facts"),
    version: asInteger(row.version, "board.card.version"),
  };
}

function toTicket(value: unknown): TicketRecord {
  const row = asRecord(value, "ticket");
  const source = asRecord(row.source, "ticket.source");
  return {
    ticketId: asString(row.ticket_id, "ticket.ticket_id"),
    title: asString(row.title, "ticket.title"),
    priority: asMember(row.priority, "ticket.priority", PRIORITIES),
    custodianId: asString(row.custodian_id, "ticket.custodian_id"),
    createdAt: asString(row.created_at, "ticket.created_at"),
    durabilityState: asMember(row.durability_state, "ticket.durability_state", DURABILITY),
    version: asInteger(row.version, "ticket.version"),
    source: {
      kind: asString(source.kind, "ticket.source.kind"),
      ref: asString(source.ref, "ticket.source.ref"),
    },
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

async function loadTicket(ticketId: string): Promise<TicketRecord> {
  return toTicket(await read(`/v1/tickets/${encodeURIComponent(ticketId)}`));
}

async function loadBoard(): Promise<BoardSnapshot> {
  const view = asRecord(await read("/v1/board"), "board");
  const cards = asArray(view.cards, "board.cards").map(toCard);
  const entries: readonly BoardEntry[] = await Promise.all(
    cards.map(async (card): Promise<BoardEntry> => {
      try {
        return { card, ticket: await loadTicket(card.ticketId) };
      } catch {
        return { card, ticket: null };
      }
    })
  );
  return {
    entries,
    health: asMember(view.health, "board.health", HEALTH),
    projectionWatermark: asInteger(view.projection_watermark, "board.projection_watermark"),
    sourceWatermark: asInteger(view.source_watermark, "board.source_watermark"),
  };
}

async function loadAudit(ticketId: string): Promise<readonly RecordEvent[]> {
  const view = asRecord(await read(`/v1/tickets/${encodeURIComponent(ticketId)}/audit`), "audit");
  return asArray(view.events, "audit.events").map(toEvent);
}

function absent(lands: string, what: string): Reading<never> {
  return { state: "absent", source: { lands, what } };
}

export const httpRecordAdapter: RecordAdapter = {
  instance: instanceIdentity(),
  board: async (): Promise<Reading<BoardSnapshot>> => await reading(loadBoard),
  ticket: async (ticketId: string): Promise<Reading<TicketRecord>> =>
    await reading(async () => await loadTicket(ticketId)),
  ticketAudit: async (ticketId: string): Promise<Reading<readonly RecordEvent[]>> =>
    await reading(async () => await loadAudit(ticketId)),
  workSessions: (): Promise<Reading<never>> =>
    Promise.resolve(
      absent("#186 / G5", "per-session work facts — seat, duration, tokens and outcome")
    ),
  cadenceRegistry: (): Promise<Reading<never>> =>
    Promise.resolve(
      absent("#186 / G5", "registered scheduled wakes, their last fire, next fire and health")
    ),
  seatInbox: (): Promise<Reading<never>> =>
    Promise.resolve(
      absent("#186", "per-seat durable messages, their read cursor and the seat addressing name")
    ),
  sessionWorkspace: (): Promise<Reading<never>> =>
    Promise.resolve(
      absent("G5", "what a session is handed at start, and its recorded state transitions")
    ),
  sessionWorktree: (): Promise<Reading<never>> =>
    Promise.resolve(absent("G5", "a session worktree's files and its diff against main")),
  authoredFiles: (): Promise<Reading<never>> =>
    Promise.resolve(absent("G5", "the authored soul, skill, guide and project file tree")),
};
