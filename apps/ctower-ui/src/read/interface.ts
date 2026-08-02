import type { BoardLane, DurabilityState, Priority, ProjectionHealth } from "@ctower/client";
import type { ReadFailure } from "./bounded";

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
 * `unavailable` — a source exists and this read did not reach it. This is never
 *                 collapsed into `absent`: an unreachable source must render as
 *                 unreachable, because "we could not read it" and "the record
 *                 does not hold it" are opposite claims to an operator.
 *
 * There is no fourth state and no default value. A screen unwraps a reading
 * only through `frame/Declared.tsx`, which renders the two non-present states
 * itself, so no surface can turn a failed read into an empty one.
 */
export type Reading<T> =
  | { readonly state: "present"; readonly value: T }
  | { readonly state: "absent"; readonly source: FutureSource }
  | { readonly state: "unavailable"; readonly failure: ReadFailure };

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

/**
 * One board card joined to the ticket read that carries its source and age.
 *
 * The join is a second read and can fail on its own, so it is kept as a
 * `Reading` rather than flattened to a nullable: a card whose ticket read did
 * not answer says so, instead of quietly showing no source and no age.
 */
export interface BoardEntry {
  readonly card: BoardCard;
  readonly ticket: Reading<TicketRecord>;
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

/* ── wave 2: the interim-source models ──────────────────────────────────────
   Each is what one screen needs and nothing more, so a native source can
   satisfy the same shape without a screen changing. */

/** What a mid-write tail did to a read of an append-only file. */
export interface TailNote {
  readonly totalLines: number;
  readonly malformed: number;
  readonly partialTail: boolean;
  readonly sourcePath: string;
}

export interface InboxMessage {
  readonly at: string;
  readonly from: string;
  readonly severity: string;
  readonly project: string | null;
  readonly subject: string;
  readonly body: string | null;
  readonly read: boolean;
  readonly wasRedacted: boolean;
}

export interface SeatSummary {
  readonly seat: string;
  readonly total: number;
  readonly unread: number;
}

export interface SeatInbox {
  readonly seats: readonly SeatSummary[];
  /** How many this seat holds in total, so a capped page never reads as all of them. */
  readonly held: number;
  readonly selected: string;
  /** The exact line that reaches this seat, quoted from the notify tool. */
  readonly addressing: string;
  readonly messages: readonly InboxMessage[];
  readonly tail: TailNote;
}

export type BeatHealth = "alive" | "late" | "dead" | "unknown";

export interface Beat {
  readonly seat: string;
  readonly beat: string;
  readonly schedule: string;
  readonly lastFire: string | null;
  readonly nextFire: string | null;
  readonly health: BeatHealth;
  readonly why: string | null;
}

export interface CadenceRegistry {
  readonly beats: readonly Beat[];
  readonly registered: number;
  readonly arriving: number;
  readonly late: number;
  readonly notArriving: number;
  /** Which source answered — `crontab` or `systemd user timers`. */
  readonly sourceLabel: string;
  readonly sweptAt: string;
}

export interface TreeEntry {
  readonly path: string;
  readonly depth: number;
  readonly isDirectory: boolean;
}

export interface CommitLine {
  readonly sha: string;
  readonly subject: string;
  readonly author: string;
  readonly at: string;
}

export interface AuthoredFiles {
  readonly root: string;
  readonly revision: string;
  readonly entries: readonly TreeEntry[];
  readonly openPath: string | null;
  readonly openLines: readonly string[];
  readonly commits: readonly CommitLine[];
}

export interface SessionWorkspace {
  readonly crew: string;
  readonly session: string;
  readonly harness: string;
  readonly cwd: string;
  readonly branch: string | null;
  readonly head: string | null;
  readonly headSubject: string | null;
  readonly project: string | null;
  readonly crews: readonly string[];
}

export interface WorktreeFile {
  readonly path: string;
  readonly status: string;
  readonly added: number | null;
  readonly removed: number | null;
}

export interface DiffLine {
  readonly text: string;
  readonly kind: "add" | "del" | "hunk" | "file" | "context";
}

export interface SessionWorktree {
  readonly root: string;
  readonly branch: string | null;
  readonly head: string | null;
  readonly base: string;
  readonly files: readonly WorktreeFile[];
  readonly diff: readonly DiffLine[];
  readonly worktrees: readonly string[];
  readonly truncated: boolean;
}

export interface PaneCapture {
  readonly crew: string;
  readonly session: string;
  readonly harness: string;
  readonly cwd: string;
  readonly lines: readonly string[];
  readonly capturedAt: string;
  readonly wasRedacted: boolean;
  readonly crews: readonly string[];
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
  cadenceRegistry: () => Promise<Reading<CadenceRegistry>>;
  /** One seat's durable inbox and its addressing name. */
  seatInbox: (seat: string | null) => Promise<Reading<SeatInbox>>;
  /** What a session was handed at start. */
  sessionWorkspace: (crew: string | null) => Promise<Reading<SessionWorkspace>>;
  /** A session worktree's files and its diff against its base. */
  sessionWorktree: (worktree: string | null) => Promise<Reading<SessionWorktree>>;
  /** The authored file tree this surface browses. */
  authoredFiles: (path: string | null) => Promise<Reading<AuthoredFiles>>;
  /** One live session pane, read-only, through the tmux capture bridge. */
  sessionPane: (crew: string | null) => Promise<Reading<PaneCapture>>;
}

/** The subset of reads the ctower read API answers today. */
export type RecordApiReads = Pick<
  RecordAdapter,
  "instance" | "board" | "ticket" | "ticketAudit" | "workSessions"
>;
