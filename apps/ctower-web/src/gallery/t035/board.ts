import type { BoardCard, BoardLane, Priority, TicketSession } from "@ctower/client";

/**
 * The parity board's facts, and where each one comes from.
 *
 * The operator's own board (`tools/ticket-crew-audit`, the reference this bench
 * is drawn against) reads a directory of files and a terminal. This one reads
 * ctower, and the whole design question is which of his thirteen columns the
 * record can answer. Four reads, three of which the console already makes:
 *
 * - `getBoard` — the card: number, title, urgency, stage, blocker, the changes
 *   made for it and how far they travelled. The same feed `ctowerctl board
 *   query` serves, which is why parity here is structural rather than a claim.
 * - `listProjectEvents` — the project's own feed, already walked by the Tickets
 *   list for the raised-at it shows. Every instant this board draws is in it:
 *   `ticket.created` is when it was raised, the newest event of any kind on a
 *   ticket's stream is when it was last touched, and the newest
 *   `workflow.changed` is when it entered the stage it stands in.
 * - `listProjectSessions` — what is running, per project. A session names its
 *   ticket, its state and its model.
 * - `exportCompanyBundle` — the company document the app already holds, whose
 *   `workflow` component declares this project's own stages in the order work
 *   moves through them. That order is the board's grouping, so a project that
 *   authors a different ladder gets a different board without a UI change.
 *
 * Two facts of his board are in none of them, and this module does not invent
 * them: which crew is at work (a run names its crew with a string the caller
 * authored, and no read turns one into the crew the company calls by name), and
 * how fast it is going (the record keeps a session's running total, never a rate
 * or a last-output instant). See the ticket's contract brief.
 */

/** The instant every frame on this bench reads against, so no shot drifts. */
export const NOW = Date.parse("2026-08-27T06:35:00Z");

/**
 * A project's ladder, in the order work moves through it.
 *
 * These are the stage keys `packs/workflows` declares and the words `words.ts`
 * already says them in. The board groups by this rather than by lane: a lane is
 * six-way and a stage is where the work actually stands, which is what the
 * operator's board groups by and what a stage-stuck ticket is stuck in.
 */
export const LADDER: readonly string[] = [
  "think",
  "plan",
  "design",
  "implement",
  "local-verification-qa",
  "risk-derived-review",
  "documentation",
  "release-preflight",
  "merge",
  "staging-deploy",
  "staging-qa",
  "production-deploy",
  "production-smoke-live-qa",
  "retro",
];

/** What a ticket with no stage is: raised, and not started. */
export const WAITING = "waiting";

/**
 * Everything one row draws, gathered from the four reads.
 *
 * Each instant is nullable because each is answered by a feed that is walked to
 * a cap: a ticket the walk did not reach keeps no time at all, and the row says
 * so rather than filing it under the oldest thing on the screen.
 */
export interface Standing {
  readonly card: BoardCard;
  /** `ticket.created`, from the project feed. */
  readonly raisedAt: string | null;
  /** The newest recorded fact on this ticket, from the same feed. */
  readonly updatedAt: string | null;
  /** The newest `workflow.changed`, which is when it entered this stage. */
  readonly enteredStageAt: string | null;
  /** Whether the feed recorded a deferral nobody has reopened. */
  readonly deferred: boolean;
  /** The open session on this ticket, when the record holds one. */
  readonly session: TicketSession | null;
  /**
   * What the day's board would draw once a run can name its crew and its rate.
   * Nothing reads either today; it is here so the two frames can be compared
   * with one component and one set of rows.
   */
  readonly ifAttributed: Attributed | null;
}

export interface Attributed {
  /** The crew the company's own roster names. */
  readonly crew: string;
  /** Tokens a minute, as the operator's board prints it. */
  readonly rate: string | null;
  /** How many times this ticket has come back from review. */
  readonly rounds: number;
}

/**
 * How a ticket is going, derived and never stamped.
 *
 * The operator's rule, in his own precedence: parked beats blocked, blocked
 * beats working, working beats stalled. A `status:` somebody typed is ignored —
 * a stamp rots the moment the thing it describes moves, which is the whole
 * reason his board computes this rather than reading it.
 *
 * `working` is the one that is weaker here than in the terminal. His board says
 * WORK when a crew is emitting tokens this minute; the record answers that a
 * session is open and says it is working, which is a claim by the session
 * rather than an observation of it.
 *
 * Two rules are narrower than the terminal's, and both are the alarm earning
 * its colour. A ticket nobody has started is **not** stalled — his board says
 * STALLED of a backlog row that has sat a while, and on a screen where amber
 * means *act on this* an untouched backlog would turn the whole board amber and
 * teach him to stop reading it. And a ticket with a session open on it is not
 * stalled either: something is on it, which is the answer the alarm was asking
 * for. Stalled means an hour in a stage, nothing at work, and nobody saying why.
 */
export type Status = "parked" | "stuck" | "working" | "stalled" | "idle";

const HOUR = 3_600_000;

export function statusOf(standing: Standing, now: number): Status {
  if (standing.deferred) {
    return "parked";
  }
  if (standing.card.blocker_reason !== null) {
    return "stuck";
  }
  if (standing.session !== null) {
    return standing.session.state === "working" ? "working" : "idle";
  }
  if (standing.card.stage_key === null) {
    return "idle";
  }
  return inStageOver(standing, now, HOUR) ? "stalled" : "idle";
}

/**
 * Whether a ticket has even begun. A row that has not is quiet on purpose: the
 * heading over it already says it is waiting to start, and repeating that in a
 * column is the console answering one question twice.
 */
export function started(standing: Standing): boolean {
  return standing.card.stage_key !== null;
}

function inStageOver(standing: Standing, now: number, span: number): boolean {
  if (standing.enteredStageAt === null) {
    return false;
  }
  const since = now - Date.parse(standing.enteredStageAt);
  return Number.isFinite(since) && since > span;
}

/** The word for each, and there is no sixth. */
const STATUS_WORD: Readonly<Record<Status, string>> = {
  parked: "Parked",
  stuck: "Stuck",
  working: "Working",
  stalled: "Stalled",
  idle: "Idle",
};

export function statusWord(status: Status): string {
  return STATUS_WORD[status];
}

/**
 * Why a ticket is not moving, in the words somebody wrote — or the loud absence
 * of them.
 *
 * The operator asked for this line by name ("how can I see the reason why ticket
 * is stuck?"), and it is the one place this board raises its voice. A stuck
 * ticket carries the reason its blocker was opened with. A stalled one carries
 * the fact that nobody gave one, because an hour in a stage with no reason is
 * the alarm his board exists to raise.
 */
export function whyOf(standing: Standing, status: Status): Why | null {
  if (status === "stuck" && standing.card.blocker_reason !== null) {
    return { kind: "named", said: standing.card.blocker_reason };
  }
  return status === "stalled" ? { kind: "unnamed" } : null;
}

export type Why = { readonly kind: "named"; readonly said: string } | { readonly kind: "unnamed" };

/**
 * How long ago, in the shortest true phrase, at the density a table wants.
 *
 * The list says `28 min` and `4 hours` because it has the room; a column three
 * characters wide says `28m` and `4h`. Same fact, same rounding, one is the
 * other abbreviated — the operator's own board adapts the same way.
 */
export function shortAge(at: string | null, now: number): string | null {
  if (at === null) {
    return null;
  }
  const since = now - Date.parse(at);
  if (!Number.isFinite(since)) {
    return null;
  }
  if (since < 60_000) {
    return "now";
  }
  if (since < HOUR) {
    return `${String(Math.floor(since / 60_000))}m`;
  }
  if (since < 24 * HOUR) {
    return `${String(Math.floor(since / HOUR))}h`;
  }
  return `${String(Math.floor(since / (24 * HOUR)))}d`;
}

/**
 * How stale a recorded instant is, as the three tones this palette has for it.
 *
 * His board decays green → plain → yellow → red. Green is spent here only on
 * things the record proved and red only on things it calls dead, so the decay
 * that survives is plain → muted → amber: fresh reads as ordinary, quiet reads
 * as quiet, and half a day without a fact reads as the one thing on the row
 * asking for attention.
 */
export type Freshness = "fresh" | "quiet" | "stale" | "unknown";

export function freshnessOf(at: string | null, now: number): Freshness {
  if (at === null) {
    return "unknown";
  }
  const since = now - Date.parse(at);
  if (!Number.isFinite(since)) {
    return "unknown";
  }
  if (since < HOUR) {
    return "fresh";
  }
  return since < 12 * HOUR ? "quiet" : "stale";
}

/** Whether a ticket has stood in one stage past the hour the operator allows. */
export function overdueInStage(standing: Standing, now: number): boolean {
  return inStageOver(standing, now, HOUR);
}

/** The rows of one stage, in the record's own order. */
export interface Pile {
  readonly stage: string;
  readonly rows: readonly Standing[];
}

/**
 * The board, grouped by stage in the project's own ladder order.
 *
 * A stage nothing stands in is not drawn. The operator's board keeps every
 * stage on its flow strip and prints only the occupied ones as groups, and this
 * follows it: the strip is where an empty stage is a fact worth seeing, and a
 * heading with nothing under it is just a gap the eye has to cross.
 */
export function pilesOf(rows: readonly Standing[], ladder: readonly string[]): readonly Pile[] {
  const order = [WAITING, ...ladder];
  return order
    .map((stage) => ({ stage, rows: rows.filter((row) => stageOf(row) === stage) }))
    .filter((pile) => pile.rows.length > 0);
}

/** Where a ticket stands: the stage it declares, or the fact it declares none. */
export function stageOf(standing: Standing): string {
  return standing.card.stage_key ?? WAITING;
}

/**
 * The stage holding the most work, which is the one the factory is waiting on.
 *
 * The operator calls it the dam and it is the whole point of the strip: a
 * pipeline's throughput is its fullest stage, and no other cell on that row
 * tells him where to send somebody. One pile alone is not a dam — a board with
 * one ticket would otherwise flag it — so it takes more than two to earn the
 * mark.
 */
export function damOf(piles: readonly Pile[]): string | null {
  const belt = piles.filter((pile) => pile.stage !== WAITING);
  const deepest = belt.reduce<Pile | null>(
    (held, pile) => (held === null || pile.rows.length > held.rows.length ? pile : held),
    null
  );
  return deepest !== null && deepest.rows.length > 2 ? deepest.stage : null;
}

/**
 * A change, said the way a person says it.
 *
 * The record keeps a repository, a web address and the change's own identity.
 * The identity is what he says out loud — "595" — and the address is what the
 * row opens; a reference that is not a web address is still drawn, because the
 * change exists either way.
 */
export function changesOf(card: BoardCard): readonly Change[] {
  return card.change_references.map((reference) => ({
    said: reference.change_identity,
    href: /^https?:\/\//.test(reference.reference) ? reference.reference : null,
    landed: card.delivery_facts.includes("change_merged"),
  }));
}

export interface Change {
  readonly said: string;
  readonly href: string | null;
  readonly landed: boolean;
}

/**
 * The model a run is on, as the product name a person says.
 *
 * `DESIGN.md` keeps product names — "Claude Code", a model's name — on the
 * surface: they are words, not wire. What it bans is the addressing around them,
 * so a reference is softened to the name and never drawn as the reference.
 */
export function modelWord(reference: string): string {
  const said = reference.replace(/^[a-z-]+[/:]/, "").replace(/[-_]/g, " ");
  return said
    .split(" ")
    .map(saidAs)
    .join(" ")
    .replace(/^Claude /, "");
}

/**
 * One word of a model's name. A short token with no vowel in it is an acronym
 * somebody says letter by letter — GPT, GLM — and title-casing one produces a
 * word nobody says.
 */
function saidAs(part: string): string {
  if (/^\d/.test(part)) {
    return part;
  }
  if (part.length <= 3 && !/[aeiou]/.test(part)) {
    return part.toUpperCase();
  }
  return part.charAt(0).toUpperCase() + part.slice(1);
}

/* ────────────────────────────────────────────────────────────────────────────
   The fixtures.

   These are ctower's own tickets as the operator's board drew them at 09:24 on
   2026-08-27, with two states added that the live board did not happen to hold
   on the hour — an urgent ticket, and a blocker somebody named — so that every
   state this design has a drawing for is on one screen at one time. They are
   `BoardCard`s, so `tsc` proves the shape is the shape `getBoard` answers with.

   One difference from his board is the record's own and worth seeing here: a
   display key is `PREFIX-N` by the authored contract, so the ticket his terminal
   calls `T-CTW-035` is `CTW-35` on a ctower board. Parity is of facts and of
   shape, never of spelling.
   ──────────────────────────────────────────────────────────────────────────── */

interface Told {
  readonly key: string;
  readonly title: string;
  readonly stage: string | null;
  readonly lane: BoardLane;
  readonly priority?: Priority;
  readonly blocker?: string;
  readonly waiting?: boolean;
  readonly change?: string;
  readonly landed?: boolean;
  readonly raised: string;
  readonly updated: string;
  readonly entered: string;
  readonly deferred?: boolean;
  readonly session?: { readonly state: TicketSession["state"]; readonly model: string };
  readonly crew?: string;
  readonly rate?: string;
  readonly rounds?: number;
}

function cardOf(told: Told): BoardCard {
  return {
    activity_class: told.stage === null ? null : "work",
    applied_labels: [],
    assignee_id: null,
    blocker_opened_at: told.blocker === undefined ? null : told.entered,
    blocker_reason: told.blocker ?? null,
    change_references:
      told.change === undefined
        ? []
        : [
            {
              change_identity: told.change,
              recorded_at: told.updated,
              reference: `https://github.com/simjak/ctower/pull/${told.change}`,
              repository: "repository:github/simjak/ctower",
            },
          ],
    custodian_id: "principal:commander",
    delivery_facts: told.landed === true ? ["change_merged"] : [],
    delivery_surface_availability: { state: "no_qualifying_checkpoint" },
    display_key: told.key,
    human_waiting:
      told.waiting === true
        ? {
            state: "waiting",
            finding_id: `finding:${told.key}`,
            kind_key: "operator_ruling",
            reason_code: "awaiting_ruling",
          }
        : { state: "not_waiting" },
    inbox_thread_ids: [],
    lane: told.lane,
    priority: told.priority ?? "P1",
    project_key: "ctower",
    risk: null,
    stage_key: told.stage,
    stage_label: told.stage,
    tenant_display_identity: { state: "known", display_name: "Jakit Labs" },
    ticket_id: `ticket-${told.key.toLowerCase()}`,
    title: told.title,
    underlying_lane: null,
    version: 4,
  };
}

function sessionOf(told: Told): TicketSession | null {
  if (told.session === undefined) {
    return null;
  }
  return {
    branch_ref: "branch:work",
    closed_at: null,
    crew_name: "authored-by-the-caller",
    duration_seconds: null,
    evidence_ref: null,
    harness_ref: "harness:claude-code",
    model_ref: told.session.model,
    outcome: null,
    project_key: "ctower",
    seat_key: "seat:unreadable",
    session_id: `session-${told.key.toLowerCase()}`,
    started_at: told.entered,
    state: told.session.state,
    ticket_id: `ticket-${told.key.toLowerCase()}`,
    tokens: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    transition_count: 1,
    worktree_ref: "worktree:work",
  };
}

function standingOf(told: Told): Standing {
  return {
    card: cardOf(told),
    raisedAt: told.raised,
    updatedAt: told.updated,
    enteredStageAt: told.entered,
    deferred: told.deferred ?? false,
    session: sessionOf(told),
    ifAttributed:
      told.crew === undefined
        ? null
        : { crew: told.crew, rate: told.rate ?? null, rounds: told.rounds ?? 0 },
  };
}

const TOLD: readonly Told[] = [
  {
    key: "CTW-35",
    title: "The command line board, the ticket card and the routines, carried as ctower's own",
    stage: "design",
    lane: "in_progress",
    raised: "2026-08-26T12:26:00Z",
    updated: "2026-08-27T06:24:00Z",
    entered: "2026-08-27T06:22:00Z",
    session: { state: "working", model: "claude-opus-5" },
    crew: "Vela",
    rate: "10.0k",
    rounds: 0,
  },
  {
    key: "CTW-40",
    title: "Rehearse the release helper upgrade against a copy of the tag it will cut",
    stage: "implement",
    lane: "in_progress",
    raised: "2026-08-26T18:02:00Z",
    updated: "2026-08-27T06:24:00Z",
    entered: "2026-08-27T05:58:00Z",
    session: { state: "working", model: "z-ai/glm-5.3" },
    crew: "Ox",
    rate: "150",
    rounds: 2,
  },
  {
    key: "CTW-20",
    title: "A scope key containing dots is legal to author but the board read refuses it",
    stage: "merge",
    lane: "in_review",
    change: "571",
    raised: "2026-08-22T18:58:00Z",
    updated: "2026-08-27T06:08:00Z",
    entered: "2026-08-26T11:20:00Z",
    crew: "Ada",
    rounds: 1,
  },
  {
    key: "CTW-37",
    title: "A client sees only his own project and his own requests, and nothing of anybody else's",
    stage: "plan",
    lane: "blocked",
    priority: "P0",
    blocker:
      "The client-scoped tenant role does not exist yet, and a viewer without it would read every project in the company.",
    waiting: true,
    raised: "2026-08-26T14:52:00Z",
    updated: "2026-08-27T05:41:00Z",
    entered: "2026-08-27T04:10:00Z",
    crew: "Ada",
    rounds: 0,
  },
  {
    key: "CTW-33",
    title: "Spool recovery is proportional to new work rather than to everything ever spooled",
    stage: "risk-derived-review",
    lane: "in_review",
    change: "592",
    landed: true,
    raised: "2026-08-25T19:30:00Z",
    updated: "2026-08-27T02:15:00Z",
    entered: "2026-08-27T02:15:00Z",
    crew: "Ox",
    rounds: 1,
  },
  {
    key: "CTW-31",
    title: "A guard so the tickets read cannot lose the project it was asked about",
    stage: "risk-derived-review",
    lane: "in_review",
    change: "588",
    raised: "2026-08-26T08:14:00Z",
    updated: "2026-08-27T03:02:00Z",
    entered: "2026-08-27T03:02:00Z",
    session: { state: "gated", model: "gpt-5.6-sol" },
    crew: "Sol",
    rounds: 1,
  },
  {
    key: "CTW-32",
    title: "The python-selection guard counts an excluded path as a path it checked",
    stage: "risk-derived-review",
    lane: "in_review",
    change: "590",
    raised: "2026-08-25T11:40:00Z",
    updated: "2026-08-27T01:20:00Z",
    entered: "2026-08-27T01:20:00Z",
    crew: "Ox",
    rounds: 3,
  },
  {
    key: "CTW-36",
    title: "The migration fixture tears its own compose project down when a run is interrupted",
    stage: "documentation",
    lane: "in_review",
    change: "596",
    landed: true,
    raised: "2026-08-26T13:11:00Z",
    updated: "2026-08-27T04:52:00Z",
    entered: "2026-08-27T04:52:00Z",
    session: { state: "gated", model: "claude-sonnet-5" },
    crew: "Luna",
    rounds: 0,
  },
  {
    key: "CTW-10",
    title: "The cockpit shell, with a pane drawn only where the record behind it is real",
    stage: null,
    lane: "backlog",
    raised: "2026-08-22T09:40:00Z",
    updated: "2026-08-26T12:31:00Z",
    entered: "2026-08-26T12:31:00Z",
    crew: "Ada",
    rounds: 1,
  },
  {
    key: "CTW-12",
    title:
      "The operator sequences the five rungs of this increment against what the next one unlocks",
    stage: null,
    lane: "backlog",
    deferred: true,
    raised: "2026-08-22T09:40:00Z",
    updated: "2026-08-27T06:08:00Z",
    entered: "2026-08-27T06:08:00Z",
    crew: "Ada",
    rounds: 0,
  },
  {
    key: "CTW-38",
    title: "A notification reaches the feed by its own route rather than by the inbox's",
    stage: null,
    lane: "backlog",
    raised: "2026-08-26T18:02:00Z",
    updated: "2026-08-26T18:02:00Z",
    entered: "2026-08-26T18:02:00Z",
    crew: "Ada",
    rounds: 2,
  },
  {
    key: "CTW-39",
    title: "Custody of a runtime credential is recorded where the runtime can be asked about it",
    stage: null,
    lane: "backlog",
    raised: "2026-08-26T18:02:00Z",
    updated: "2026-08-26T18:02:00Z",
    entered: "2026-08-26T18:02:00Z",
    crew: "Ada",
    rounds: 2,
  },
];

/** The board as ctower's own project stands, for every frame on this bench. */
export const ROWS: readonly Standing[] = TOLD.map(standingOf);

/**
 * The same project on a morning the reads answer less.
 *
 * Nothing is running, so no row names a model. And the feed is read oldest
 * first and walked to a cap, so it is the *newest* tickets whose facts the walk
 * never reached: the three raised last keep no time at all. It is the state a
 * live tower is in more often than the full one, and a board that only looks
 * right when every read is generous is a board that looks broken on an ordinary
 * Tuesday.
 */
const UNREACHED: ReadonlySet<string> = new Set(
  [...ROWS]
    .sort((first, second) => (second.raisedAt ?? "").localeCompare(first.raisedAt ?? ""))
    .slice(0, 3)
    .map((row) => row.card.ticket_id)
);

export const THIN_ROWS: readonly Standing[] = ROWS.map((row) => {
  const unread = UNREACHED.has(row.card.ticket_id);
  return {
    ...row,
    session: null,
    raisedAt: unread ? null : row.raisedAt,
    updatedAt: unread ? null : row.updatedAt,
    enteredStageAt: unread ? null : row.enteredStageAt,
  };
});
