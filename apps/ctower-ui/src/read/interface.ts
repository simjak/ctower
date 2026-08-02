import type { BoardLane, DurabilityState, Priority, ProjectionHealth } from "@ctower/client";
import type { ReadFailure } from "./bounded";
import type { Known } from "./sources/maybe";

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
  /** The seat behind the custodian principal, when the record names one. */
  readonly custodianName: string | null;
  readonly assigneeId: string | null;
  readonly assigneeName: string | null;
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
  readonly custodianName: string | null;
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
  /** The derivation the source used, so the screen states it without knowing it. */
  readonly healthRule: string;
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
  /** Files the revision holds, and how many of them this page is showing. */
  readonly sourceTotal: number;
  readonly shownTotal: number;
  readonly truncated: boolean;
  readonly openPath: string | null;
  readonly openLines: readonly string[];
  readonly commits: readonly CommitLine[];
}

/**
 * One labelled fact a screen renders without knowing where it came from.
 *
 * Round-1 review found the screens hardcoding interim-source vocabulary —
 * `bin/mux spawn`, "tmux session", "capture bridge" — which made the
 * adapter-only swap claim untrue. A source now *names* its own facts, and the
 * screen renders whatever it is handed, so a native source can replace an
 * interim one without a screen edit or a false label.
 */
export interface LabelledFact {
  readonly label: string;
  readonly value: Known<string>;
  readonly detail: string | null;
}

export interface SessionWorkspace {
  /** The selected subject, and the choices the source offers for it. */
  readonly chosen: string;
  readonly choices: readonly string[];
  readonly facts: readonly LabelledFact[];
  /** How this session was started, when the source records it. */
  readonly startCommand: Known<string>;
  /** What the source calls itself, for the panel subtitle. */
  readonly sourceNote: string;
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
  /** Worktrees git still lists whose directory is gone; reaped, not shown. */
  readonly reaped: number;
  readonly openPath: string | null;
  readonly openDiff: readonly DiffLine[];
  readonly openDiffRead: Known<string>;
  readonly branch: Known<string>;
  readonly head: Known<string>;
  readonly base: string;
  readonly files: readonly WorktreeFile[];
  /** Whether the file stat answered — an unread stat is not a clean tree. */
  readonly filesRead: Known<string>;
  readonly diff: readonly DiffLine[];
  readonly diffRead: Known<string>;
  readonly worktrees: readonly string[];
  readonly truncated: boolean;
}

/** One turn of a session stream, whatever produced it. */
export interface StreamTurn {
  readonly body: readonly string[];
  readonly tools: readonly StreamTool[];
}

export interface StreamTool {
  readonly summary: string;
  readonly output: readonly string[];
}

/**
 * A session as a stream of turns. Source-neutral: a terminal capture and a
 * typed G5 turn stream both satisfy it, and the screen renders `header`,
 * `turns` and `rawLines` without knowing which answered.
 */
export interface SessionStream {
  readonly chosen: string;
  readonly choices: readonly string[];
  readonly header: readonly LabelledFact[];
  readonly turns: readonly StreamTurn[];
  readonly rawLines: readonly string[];
  readonly observedAt: string;
  readonly wasRedacted: boolean;
  /** What this stream is, said by the source: honest about its own fidelity. */
  readonly fidelityNote: string;
}

/* ── S9 metrics ────────────────────────────────────────────────────────── */

export interface MergeDay {
  readonly day: string;
  readonly count: number;
}

export interface ProjectMerges {
  readonly key: string;
  readonly label: string;
  /** The ref counted, named so the derivation is inspectable. */
  readonly trunk: string;
  readonly days: readonly MergeDay[];
  readonly landed: number;
  readonly reverted: number;
}

/**
 * One delivery card. `value === null` means the record this measure needs does
 * not exist — the card says so and names what would land it, rather than
 * showing a zero that reads as a measurement.
 */
export interface DeliveryMeasure {
  readonly title: string;
  readonly value: string | null;
  readonly unit: string | null;
  readonly target: string;
  readonly note: string;
  readonly source: string;
  /** Present only when the measure has no record: what would land it. */
  readonly lands?: string;
}

/** One project tab's worth of the page: its own cards, bars and legend. */
export interface DeliveryScope {
  /** `all`, or a project key; matches the scope radio the vendored CSS keys on. */
  readonly key: string;
  readonly label: string;
  readonly measures: readonly DeliveryMeasure[];
  readonly projects: readonly ProjectMerges[];
}

export interface DeliveryMetrics {
  readonly scopes: readonly DeliveryScope[];
  readonly projects: readonly ProjectMerges[];
  readonly windowDays: readonly string[];
  /** Projects whose history could not be read, so a total can be sized. */
  readonly unread: number;
  readonly considered: number;
  readonly reason: string | null;
  readonly measuredAt: string;
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
  sessionWorktree: (
    worktree: string | null,
    path: string | null
  ) => Promise<Reading<SessionWorktree>>;
  /** The authored file tree this surface browses. */
  authoredFiles: (path: string | null) => Promise<Reading<AuthoredFiles>>;
  /** One live session pane, read-only, through the tmux capture bridge. */
  sessionStream: (subject: string | null) => Promise<Reading<SessionStream>>;
  /** Delivery measured per project: what the record supports, and what it does not. */
  deliveryMetrics: () => Promise<Reading<DeliveryMetrics>>;
}

/** The subset of reads the ctower read API answers today. */
export type RecordApiReads = Pick<
  RecordAdapter,
  "instance" | "board" | "ticket" | "ticketAudit" | "workSessions"
>;
