// Driver for the cross-project portfolio fold.
//
// The director's sweep is one screen over three project boards and one inbox,
// and every number on it is a count. A count is the easiest thing on a surface
// to get quietly wrong — a lane dropped, a failed board folded in as zero,
// unread mail attributed to a project the record never linked it to — and the
// wrongness is invisible, because a plausible number looks exactly like a true
// one.
//
// So this drives the real `read/portfolioProjection.ts` over fixed card
// payloads and emits BOTH the projection's output and the payloads it was
// given. `test_portfolio_projection.py` recounts the payloads itself, in
// Python, and asserts the two agree — an independent recount rather than a
// re-execution of the same expression.
//
// Nothing here runs a command, reads a file, opens a socket or reads a clock.

import { portfolioOf } from "../../apps/ctower-ui/src/read/portfolioProjection.ts";
import type { PortfolioBoardRead } from "../../apps/ctower-ui/src/read/portfolioProjection.ts";
import { LANES } from "../../apps/ctower-ui/src/read/interface.ts";
import { LANE_COLUMNS } from "../../apps/ctower-ui/src/surfaces/board/lanes.ts";
import type {
  BoardCard,
  BoardCards,
  BoardLane,
  InboxProjection,
  Reading,
} from "../../apps/ctower-ui/src/read/interface.ts";

const results: Record<string, unknown> = {};

const OBSERVED = "2026-08-08T19:45:00.000Z";
const THREAD_A = "018f0d5e-7b9a-7c01-8000-0000000000a1";
const THREAD_B = "018f0d5e-7b9a-7c01-8000-0000000000b2";
const THREAD_C = "018f0d5e-7b9a-7c01-8000-0000000000c3";

/** The payload shape the recount in Python reads back out of this driver. */
interface CardSpec {
  readonly lane: BoardLane;
  readonly staged: boolean;
  readonly waiting: boolean;
  readonly threads: readonly string[];
}

let nextTicket = 0;

function card(projectKey: string, spec: CardSpec): BoardCard {
  nextTicket += 1;
  const serial = nextTicket.toString().padStart(4, "0");
  return {
    ticketId: `018f0d5e-7b9a-7c01-8000-00000000${serial}`,
    projectKey,
    title: `${projectKey} ticket ${serial}`,
    lane: spec.lane,
    priority: "P2",
    stageKey: spec.staged ? "close" : null,
    stageLabel: spec.staged ? "close" : null,
    activityClass: null,
    custodianId: "018f0d5e-7b9a-7c01-8000-0000000000ff",
    custodianName: null,
    assigneeId: null,
    assigneeName: null,
    blockerReason: null,
    blockerOpenedAt: null,
    risk: null,
    deliveryFacts: [],
    inboxThreadIds: spec.threads,
    tenantDisplayIdentity: { state: "unknown", missingSource: "tenant.display_name" },
    changeReferences: [],
    appliedLabels: [],
    humanWaiting: spec.waiting
      ? {
          state: "waiting",
          finding_id: `018f0d5e-7b9a-7c01-8000-0000000f${serial}`,
          kind_key: "needs_visual_qa",
          reason_code: "vision_path_deferred",
        }
      : { state: "not_waiting" },
    deliverySurfaceAvailability: { state: "no_qualifying_checkpoint" },
    version: 1,
  } as unknown as BoardCard;
}

function present(projectKey: string, specs: readonly CardSpec[]): Reading<BoardCards> {
  return {
    state: "present",
    value: {
      cards: specs.map((spec) => card(projectKey, spec)),
      health: "CURRENT",
      projectionWatermark: 657,
      sourceWatermark: 657,
      scope: { projectKey },
    },
  };
}

function unreachable(reason: string): Reading<BoardCards> {
  return {
    state: "unavailable",
    failure: { reason, failureClass: "transient", attempts: 3, elapsedMs: 4210, status: null },
  };
}

function boardRead(key: string, board: Reading<BoardCards>): PortfolioBoardRead {
  return { key, boardHref: `/board?project=${encodeURIComponent(key)}`, board };
}

/* ── the payloads ─────────────────────────────────────────────────────────
   Deliberately lopsided, and deliberately not uniform per lane: a fold that
   silently used the first project's shape, or that counted a lane by index
   rather than by name, still has to reproduce these exact numbers. */

const MANIBO: readonly CardSpec[] = [
  { lane: "backlog", staged: false, waiting: false, threads: [] },
  { lane: "backlog", staged: false, waiting: false, threads: [THREAD_A] },
  { lane: "backlog", staged: false, waiting: true, threads: [] },
  { lane: "ready", staged: false, waiting: false, threads: [] },
  { lane: "in_review", staged: true, waiting: false, threads: [] },
];

const CTOWER: readonly CardSpec[] = [
  { lane: "backlog", staged: false, waiting: false, threads: [] },
  { lane: "backlog", staged: false, waiting: false, threads: [] },
  { lane: "backlog", staged: false, waiting: false, threads: [] },
  { lane: "in_progress", staged: true, waiting: false, threads: [THREAD_B] },
  { lane: "in_progress", staged: false, waiting: true, threads: [THREAD_B] },
  { lane: "blocked", staged: false, waiting: true, threads: [] },
  { lane: "complete", staged: true, waiting: false, threads: [] },
  { lane: "complete", staged: true, waiting: false, threads: [] },
];

const BHLOOP: readonly CardSpec[] = [
  { lane: "backlog", staged: false, waiting: false, threads: [] },
];

const INBOX: InboxProjection = {
  recipient: "designer",
  threads: [
    {
      threadId: THREAD_A,
      otherAgent: "commander",
      lastMessagePreview: "manibo's intake needs a second look",
      lastMessageAt: "2026-08-08T18:00:00Z",
      unreadCount: 2,
      promotedTicketId: null,
    },
    {
      threadId: THREAD_B,
      otherAgent: "engineer",
      lastMessagePreview: "the promote control is server-mediated now",
      lastMessageAt: "2026-08-08T18:30:00Z",
      unreadCount: 3,
      promotedTicketId: null,
    },
    {
      threadId: THREAD_C,
      otherAgent: "reviewer",
      lastMessagePreview: "no board card names this thread",
      lastMessageAt: "2026-08-08T18:45:00Z",
      unreadCount: 4,
      promotedTicketId: null,
    },
  ],
  totalUnread: 9,
  unreadOnly: false,
};

const inboxPresent: Reading<InboxProjection> = { state: "present", value: INBOX };

/* ── the axis contract ────────────────────────────────────────────────────
   The screen renders its columns from the Board's own LANE_COLUMNS and the
   projection emits one entry per LANES member. If those two sets ever diverge
   a lane silently stops being a column, and its cards vanish from a matrix
   whose row total still counts them. */

results.laneAxis = [...LANES];
results.laneColumns = LANE_COLUMNS.map((column) => column.lane);
results.laneColumnTitles = LANE_COLUMNS.map((column) => column.title);

/* ── the whole-fleet answer ───────────────────────────────────────────────  */

results.payload = {
  manibo: MANIBO,
  ctower: CTOWER,
  "bh-loop": BHLOOP,
  inbox: INBOX,
};

results.portfolio = portfolioOf(
  [
    boardRead("manibo", present("manibo", MANIBO)),
    boardRead("ctower", present("ctower", CTOWER)),
    boardRead("bh-loop", present("bh-loop", BHLOOP)),
  ],
  inboxPresent,
  OBSERVED
);

/* ── one board down ───────────────────────────────────────────────────────
   The row that failed must not contribute a zero to any total, must not be
   counted as answered, and must not silently take an unread attribution it
   has no cards to justify. */

results.oneBoardUnreachable = portfolioOf(
  [
    boardRead("manibo", unreachable("the read API answered 503")),
    boardRead("ctower", present("ctower", CTOWER)),
    boardRead("bh-loop", present("bh-loop", BHLOOP)),
  ],
  inboxPresent,
  OBSERVED
);

/* ── nothing answered ─────────────────────────────────────────────────────
   Reaching none of the sources is still an answer this screen can render:
   three rows saying not-reached and `0 of 3`. It is never an empty portfolio. */

results.noBoardAnswered = portfolioOf(
  [
    boardRead("manibo", unreachable("the read API answered 503")),
    boardRead("ctower", unreachable("the read attempt timed out")),
    boardRead("bh-loop", unreachable("the read attempt timed out")),
  ],
  inboxPresent,
  OBSERVED
);

/* ── the inbox did not answer ─────────────────────────────────────────────  */

results.inboxUnreachable = portfolioOf(
  [
    boardRead("manibo", present("manibo", MANIBO)),
    boardRead("ctower", present("ctower", CTOWER)),
    boardRead("bh-loop", present("bh-loop", BHLOOP)),
  ],
  {
    state: "unavailable",
    failure: {
      reason: "the read API answered 401",
      failureClass: "permanent",
      attempts: 1,
      elapsedMs: 12,
      status: 401,
    },
  },
  OBSERVED
);

/* ── the principal that holds no address ──────────────────────────────────
   Live today: the surface's own credential has no project-seat row, so the
   projection names it `unaddressable`. Zero unread there is not an empty
   inbox — it is an inbox nothing can be delivered to, and the two must not
   render as each other. */

results.unaddressablePrincipal = portfolioOf(
  [boardRead("bh-loop", present("bh-loop", BHLOOP))],
  {
    state: "present",
    value: { recipient: "unaddressable", threads: [], totalUnread: 0, unreadOnly: false },
  },
  OBSERVED
);

results.addressablePrincipalWithNoMail = portfolioOf(
  [boardRead("bh-loop", present("bh-loop", BHLOOP))],
  {
    state: "present",
    value: { recipient: "designer", threads: [], totalUnread: 0, unreadOnly: false },
  },
  OBSERVED
);

/* ── a project the fleet adds later ───────────────────────────────────────
   The screen renders whatever rows the fold is handed, so a fourth project
   needs no view change: one more entry in `read/projects.ts` is one more row. */

results.fourthProjectNeedsNoViewChange = portfolioOf(
  [
    boardRead("manibo", present("manibo", MANIBO)),
    boardRead("ctower", present("ctower", CTOWER)),
    boardRead("bh-loop", present("bh-loop", BHLOOP)),
    boardRead("new-project", present("new-project", [MANIBO[0] as CardSpec])),
  ],
  inboxPresent,
  OBSERVED
).projects.map((project) => project.key);

process.stdout.write(JSON.stringify(results, null, 2));
