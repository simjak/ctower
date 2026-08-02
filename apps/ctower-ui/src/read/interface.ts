import type { BoardLane, DurabilityState, Priority, ProjectionHealth } from "@ctower/client";

/**
 * The record-read contract this surface renders.
 *
 * Phase 1 reads the shadow instance's existing read API. When the #186 typed
 * feed lands, only `src/read/adapter.ts` changes: every screen already speaks
 * these functions and this `Reading` union, so no surface is edited to swap the
 * source.
 *
 * Lane, priority, durability and projection-health are the generated contract's
 * own literal unions, so a value this surface renders cannot drift from the
 * authored schema without a compile failure.
 */

export type { BoardLane, DurabilityState, Priority, ProjectionHealth };

export const LANES: readonly BoardLane[] = [
  "backlog",
  "ready",
  "in_progress",
  "in_review",
  "blocked",
  "complete",
];

/** A fact ctower does not record yet, named by the work that will record it. */
export interface FutureSource {
  /** The work item that lands the source, e.g. `#186` or `G5`. */
  readonly lands: string;
  /** What that work will start recording, in operator language. */
  readonly what: string;
}

/**
 * One read outcome.
 *
 * `present`     — the record answered and the value is what it recorded.
 * `absent`      — ctower records no such fact yet; `source` names what will.
 * `unavailable` — a source exists but this read did not succeed; never blank.
 */
export type Reading<T> =
  | { readonly state: "present"; readonly value: T }
  | { readonly state: "absent"; readonly source: FutureSource }
  | { readonly state: "unavailable"; readonly reason: string };

export interface RecordSource {
  readonly kind: string;
  readonly ref: string;
}

export interface BoardCard {
  readonly ticketId: string;
  readonly title: string;
  readonly lane: BoardLane;
  readonly priority: Priority;
  readonly stageKey: string | null;
  readonly stageLabel: string | null;
  readonly activityClass: string | null;
  readonly custodianId: string;
  readonly assigneeId: string | null;
  readonly blockerReason: string | null;
  readonly blockerOpenedAt: string | null;
  readonly risk: string | null;
  readonly deliveryFacts: readonly string[];
  readonly version: number;
}

export interface TicketRecord {
  readonly ticketId: string;
  readonly title: string;
  readonly priority: Priority;
  readonly custodianId: string;
  readonly createdAt: string;
  readonly durabilityState: DurabilityState;
  readonly version: number;
  readonly source: RecordSource;
}

/** One board card joined to the ticket read that carries its source and age. */
export interface BoardEntry {
  readonly card: BoardCard;
  readonly ticket: TicketRecord | null;
}

export interface BoardSnapshot {
  readonly entries: readonly BoardEntry[];
  readonly health: ProjectionHealth;
  readonly projectionWatermark: number;
  readonly sourceWatermark: number;
}

export interface RecordEvent {
  readonly eventId: string;
  readonly sequence: number;
  readonly kind: string;
  readonly occurredAt: string;
  readonly actorPrincipalId: string;
  readonly commandId: string;
  readonly streamId: string | null;
  readonly eventHash: string | null;
  readonly recordPosition: number | null;
  readonly payload: Record<string, unknown>;
}

/** Which ctower instance this surface is reading, for the header and the foot. */
export interface InstanceIdentity {
  readonly label: string;
  readonly posture: string;
  readonly baseUrl: string;
}

/**
 * Every read this surface makes. One module implements it; screens import the
 * selected implementation from `adapter.ts` and never construct their own.
 */
export interface RecordAdapter {
  readonly instance: InstanceIdentity;
  board: () => Promise<Reading<BoardSnapshot>>;
  ticket: (ticketId: string) => Promise<Reading<TicketRecord>>;
  ticketAudit: (ticketId: string) => Promise<Reading<readonly RecordEvent[]>>;
  /** Per-session work facts: who, duration, tokens, outcome. */
  workSessions: (ticketId: string) => Promise<Reading<never>>;
  /** Registered scheduled wakes and their fire history. */
  cadenceRegistry: () => Promise<Reading<never>>;
  /** One seat's durable inbox and its addressing name. */
  seatInbox: () => Promise<Reading<never>>;
  /** What a session was handed at start, and its state transitions. */
  sessionWorkspace: () => Promise<Reading<never>>;
  /** A session worktree's files and its diff against main. */
  sessionWorktree: () => Promise<Reading<never>>;
  /** The authored file tree this surface would edit. */
  authoredFiles: () => Promise<Reading<never>>;
}
