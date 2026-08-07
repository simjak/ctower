import type {
  AppliedLabel,
  BoardLane,
  ChangeReference,
  DeliverySurfaceAvailability,
  DurabilityState,
  HumanWaiting,
  Priority,
  ProjectionHealth,
} from "@ctower/client";
import type { ReadFailure } from "./bounded";
import type { Known } from "./sources/maybe";

/**
 * The record-read contract this surface renders.
 *
 * Phase 1 reads the shadow instance's existing read API. When a typed feed
 * lands, only `src/read/adapter.ts` changes: every screen already speaks these
 * functions and this `Reading` union, so no surface is edited to swap the
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

/**
 * A fact this surface has nothing to show for, and *why* it has nothing.
 *
 * The two reasons are opposite claims to an operator and are never merged:
 *
 * * `capability` — ctower records no fact of this class yet. When a work item is
 *   filed to land it, `lands` names that item and `why` says how it covers this
 *   exact fact. When none is filed, `lands` is `null` and the surface says so —
 *   round-3 QA (#241) found nine unrelated panels all citing one issue that
 *   covered none of them, which is worse than citing nothing.
 * * `silence` — ctower does record this class of fact and holds none for this
 *   subject. Nothing needs to land, so there is nothing to cite.
 *
 * Every instance is declared once in `read/futureSources.ts`; no screen builds
 * one inline, so a citation cannot be minted without passing that table.
 */
export type FutureSource =
  | {
      readonly absence: "capability";
      /** What ctower does not record, in operator language. */
      readonly what: string;
      /** The work item that would land it, or `null` when none is filed. */
      readonly lands: string | null;
      /** How that item covers this fact; `null` when nothing is cited. */
      readonly why: string | null;
    }
  | {
      readonly absence: "silence";
      /** The recorded fact this subject holds none of, in operator language. */
      readonly what: string;
    };

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
  /**
   * The issue this ticket was raised from, when the recorded source kind is an
   * issue tracker and the ref parses as one of its references.
   *
   * The operator asked the board to reflect the issue a ticket is linked to.
   * That link is only ever the record's own `source` — this surface resolves a
   * URL from a kind it recognises and a ref that parses, and renders the raw ref
   * as text otherwise. A repository guessed from an identifier's spelling would
   * be the inference INV-66 forbids, and a URL guessed from it would be a
   * fabricated link an operator would click.
   */
  readonly issue: IssueReference | null;
}

/** One resolved issue reference: where it lives, and the address to open. */
export interface IssueReference {
  /** `owner/repo`, exactly as the ref recorded it. */
  readonly repository: string;
  readonly number: number;
  readonly url: string;
  /** How it reads on a card: `owner/repo#123`. */
  readonly label: string;
}

/**
 * The tenant a ticket's work is for, per gh#115/D29 — one of the Board card's
 * five context-set members. `known`/`unknown` are both explicit facts: an
 * unattributed ticket says so rather than rendering blank, the same rule
 * INV-66 already holds every other member of this set to.
 *
 * This is not the `project` axis: `tenant_display_identity` is the
 * client/company a ticket's work is for, while `project_key` says which
 * configured project owns the ticket.
 */
export type TenantDisplayIdentity =
  | { readonly state: "known"; readonly displayName: string }
  | { readonly state: "unknown"; readonly missingSource: string };

export interface BoardCard {
  readonly ticketId: string;
  readonly projectKey: string;
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
  readonly tenantDisplayIdentity: TenantDisplayIdentity;
  readonly changeReferences: readonly ChangeReference[];
  readonly appliedLabels: readonly AppliedLabel[];
  readonly humanWaiting: HumanWaiting;
  readonly deliverySurfaceAvailability: DeliverySurfaceAvailability;
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
  /** What this read asked for, and what the record could answer with. */
  readonly scope: BoardScope;
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
  /**
   * Beats whose liveness could not be established, counted rather than left as
   * the remainder of a subtraction. Round-3 QA (#238) found four tiles summing
   * to four of five registered beats, so the operator had to notice the missing
   * one by arithmetic.
   */
  readonly unaccounted: number;
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

/**
 * What a worktree diff was measured against.
 *
 * A base is not a constant. Round-3 QA (#236) found every diff taken against the
 * checkout's bare local `main`, which was 25 commits behind the trunk, so a
 * six-file branch rendered as 267 files. The base therefore carries its own
 * commit and the sentence explaining how it was chosen, and both are printed —
 * a stale base is visible rather than silent.
 */
export interface DiffBase {
  /** The ref git was asked to diff against, when one resolved. */
  readonly ref: Known<string>;
  /** That ref's own commit, so the reader can see how old the base is. */
  readonly head: Known<string>;
  /** How this base was chosen, in operator language. */
  readonly note: string;
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
  readonly base: DiffBase;
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
  /**
   * The source's own status lines — a spinner, an elapsed-time tick, a scheduled
   * wake. They are attached to the turn they interrupt rather than promoted to
   * turns of their own: round-3 QA (#242) found five of eleven bubbles on one
   * screenful carrying nothing a reader wants.
   */
  readonly notes: readonly string[];
}

export interface StreamTool {
  readonly summary: string;
  readonly output: readonly string[];
}

/**
 * A session as a stream of turns. Source-neutral: a terminal capture and a
 * typed turn stream both satisfy it, and the screen renders `header`,
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

/* ── the who layer ─────────────────────────────────────────────────────────
   A **seat** is durable: one accountable persona that outlives every job it
   does. A **crew** is one engagement of that seat — a live session with a
   model, a project and one task. The roster counts crews; it never invents a
   seat that no source declares, and it never fills a field the record is
   silent about. */

/**
 * How a crew's recorded status word classifies to the product's three marks.
 * `unrecorded` is its own case: a crew with no status is not a parked crew.
 */
export type CrewActivity = "in-flight" | "parked" | "held" | "unrecorded";

/** One live crew, as the fleet holds it. */
export interface CrewRow {
  /** The crew name the naming rule parses, with the mux prefix already removed. */
  readonly name: string;
  /** The tmux session name, unstripped — what a pane read must ask tmux for. */
  readonly sessionName: string;
  /** What the name parses to. A name that does not parse says so, per part. */
  readonly seat: Known<string>;
  readonly seatLabel: Known<string>;
  /** The seat's two-letter mark, so two seats never share one avatar. */
  readonly seatInitials: Known<string>;
  readonly request: Known<string>;
  readonly slug: Known<string>;
  readonly project: Known<string>;
  readonly model: Known<string>;
  readonly harness: Known<string>;
  readonly task: Known<string>;
  /** The status word the log recorded, not a word this surface chose. */
  readonly status: Known<string>;
  readonly activity: CrewActivity;
  readonly upFor: Known<string>;
  readonly loggedAgo: Known<string>;
  /** A standing rule this row's own record contradicts, stated on the row. */
  readonly flag: string | null;
}

/** One project's crews, grouped as the roster shows them. */
export interface ProjectRoster {
  readonly key: string;
  readonly label: string;
  readonly crews: readonly CrewRow[];
  readonly inFlight: number;
  readonly parked: number;
  readonly held: number;
}

/** One row of the seats × projects grid. */
export interface SeatRow {
  readonly seat: string;
  readonly label: string;
  readonly initials: string;
  /** Aligned with `CrewRoster.columns`. */
  readonly perProject: readonly number[];
  readonly total: number;
}

/** One model's share of the live crews, with the harness that runs it. */
export interface ModelShare {
  readonly label: string;
  readonly harness: Known<string>;
  readonly count: number;
}

/** A filter the roster offers, with the count it would reveal. */
export interface RosterFilter {
  readonly key: string;
  readonly label: string;
  readonly count: number;
}

export interface CrewRoster {
  /** Project labels, in grid-column order. */
  readonly columns: readonly string[];
  readonly seats: readonly SeatRow[];
  readonly columnTotals: readonly number[];
  readonly total: number;
  readonly groups: readonly ProjectRoster[];
  readonly projectFilters: readonly RosterFilter[];
  readonly seatFilters: readonly RosterFilter[];
  /** What clearing one filter would reveal, with the other one left alone. */
  readonly allProjectsCount: number;
  readonly allSeatsCount: number;
  readonly selectedProject: string | null;
  readonly selectedSeat: string | null;
  readonly inFlight: number;
  readonly parked: number;
  readonly held: number;
  readonly unrecorded: number;
  readonly models: readonly ModelShare[];
  /** Crews the seat list could not account for, so a total can be sized. */
  readonly unseated: number;
  readonly observedAt: string;
  /** Where the seat list came from, said by the source. */
  readonly seatSource: string;
  /** The status→mark classification, stated so the screen need not know it. */
  readonly activityRule: string;
  readonly sourceNote: string;
  readonly tail: TailNote;
}

/* ── one crew in full ──────────────────────────────────────────────────────
   The roster answers "who is working". A profile answers "what has this one
   crew done, and who stands behind it". Same three sources, plus the records a
   seat writes about itself: its status files, and the ledger that charges an
   escape to its seat. Nothing here is derived from a name the way a shell page
   would be — a field no record carries is `none` with the reason, and a field
   whose read failed is `unread`. */

/** One recorded step of a crew's life, as the crew log holds it. */
export interface CrewLifecycleEntry {
  /** The stamp the log wrote, verbatim. */
  readonly at: string;
  readonly ago: Known<string>;
  readonly status: Known<string>;
  readonly activity: CrewActivity;
  readonly task: Known<string>;
  readonly model: Known<string>;
  readonly comment: Known<string>;
  /** This entry's task differs from the one before it: a new engagement. */
  readonly opensEngagement: boolean;
}

/**
 * Whether a project's trunk carries a change this crew's own records claim.
 * `unchecked` is its own case: no trunk was read, so nothing is being said
 * about the change either way.
 */
export type LandedVerdict = "landed" | "not-on-trunk" | "unchecked";

export interface DeliveredChange {
  /** The reference as the crew wrote it, e.g. `#215`. */
  readonly reference: string;
  /** Which of the crew's own records named it. */
  readonly citedIn: string;
  /** The project that record was filed under: whose trunk decided the verdict. */
  readonly project: Known<string>;
  /** True when that project is the crew's, because the record named none. */
  readonly projectFromCrew: boolean;
  readonly verdict: LandedVerdict;
  readonly verdictLabel: string;
  /** The trunk entry that carries it, or why no verdict could be reached. */
  readonly detail: Known<string>;
}

/** One `SIGNED-OFF` block, quoted from the file the crew wrote it in. */
export interface SignedClaim {
  readonly file: string;
  readonly seat: Known<string>;
  readonly model: Known<string>;
  readonly claim: Known<string>;
  readonly stoodUnder: Known<string>;
  readonly ifThisBreaks: Known<string>;
}

/** The three rungs of the fleet's autonomy ladder, in descending trust. */
export type LadderRung = "TRUSTED" | "WATCHED" | "GROUNDED";

export interface LadderStep {
  readonly rung: LadderRung;
  readonly label: string;
  /** What the rung permits, in the ladder's own words. */
  readonly what: string;
  readonly entered: string;
}

export interface Accountability {
  readonly rung: LadderRung;
  readonly steps: readonly LadderStep[];
  readonly escapes: Known<number>;
  /**
   * False when the ledger charges this seat nothing and the rung is therefore
   * the ladder's default rather than a state anybody recorded. The screen says
   * which it is; a default drawn as a measurement is the lie this flag exists
   * to stop.
   */
  readonly counted: boolean;
  readonly defaultNote: string | null;
  /** The escapes charged to this seat, quoted. */
  readonly charged: readonly string[];
  readonly ledgerSource: string;
  readonly ruleSource: string;
  readonly scopeNote: string;
}

/** A destination inside this surface that exists for this crew. */
export interface CrewLink {
  readonly label: string;
  readonly href: string;
  readonly what: string;
}

export interface CrewProfile {
  /** The identity facts, in exactly the shape the roster row carries them. */
  readonly row: CrewRow;
  readonly sessionName: string;
  readonly spawnedAt: Known<string>;
  /** How long since this session last produced output, as tmux records it. */
  readonly lastOutput: Known<string>;
  readonly worktree: Known<string>;
  readonly branch: Known<string>;
  readonly head: Known<string>;
  readonly headSubject: Known<string>;
  readonly running: Known<string>;
  readonly links: readonly CrewLink[];
  readonly lifecycle: readonly CrewLifecycleEntry[];
  /** How many entries the log holds for this crew, and how many are shown. */
  readonly lifecycleNote: string;
  readonly delivered: readonly DeliveredChange[];
  readonly deliveredNote: string;
  readonly claims: readonly SignedClaim[];
  /** Every signature found, so quoting a few never reads as quoting them all. */
  readonly signatures: number;
  readonly claimsNote: string;
  readonly accountability: Accountability;
  /** What would record this crew's cost. Always absent; never a number. */
  readonly cost: FutureSource;
  readonly observedAt: string;
  readonly sourceNote: string;
  readonly tail: TailNote;
}

/** A name the fleet does not run, and everything that was checked for it. */
export interface CrewUnknown {
  readonly crew: string;
  /** What the crew log holds for the name, when it holds anything. */
  readonly logged: Known<string>;
  readonly liveCrews: number;
  /** The sources consulted, named, so the answer can be re-derived by hand. */
  readonly checked: readonly string[];
}

/**
 * A profile read. Not finding a crew is an answer, not a failure: the sources
 * were reached and none of them runs this name. It stays inside `present` so
 * the screen can say what *was* found, and an unreachable tmux stays a separate
 * `unavailable` claim.
 */
export type CrewLookup =
  | { readonly found: "crew"; readonly profile: CrewProfile }
  | { readonly found: "no-such-crew"; readonly missing: CrewUnknown };

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
 * How a board read was scoped, so the screen can say what it is looking at.
 *
 * The read is always scoped by project key — that is the contract's required
 * parameter — and every parsed Board card carries the same project fact.
 */
export interface BoardScope {
  /** The project key the read asked for. */
  readonly projectKey: string;
}

/**
 * Every read this surface makes. One module implements it; screens import the
 * selected implementation from `adapter.ts` and never construct their own.
 */
export interface RecordAdapter {
  readonly instance: InstanceIdentity;
  board: (projectKey: string) => Promise<Reading<BoardSnapshot>>;
  ticket: (ticketId: string, projectKey: string) => Promise<Reading<TicketRecord>>;
  ticketAudit: (ticketId: string, projectKey: string) => Promise<Reading<readonly RecordEvent[]>>;
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
  /** Who is working, on what: seats down, projects across, then every live crew. */
  crewRoster: (project: string | null, seat: string | null) => Promise<Reading<CrewRoster>>;
  /** One crew in full: what it is, what it has done, and who stands behind it. */
  crewProfile: (crew: string) => Promise<Reading<CrewLookup>>;
}

/** The subset of reads the ctower read API answers today. */
export type RecordApiReads = Pick<
  RecordAdapter,
  "instance" | "board" | "ticket" | "ticketAudit" | "workSessions"
>;
