import { LANES } from "./interface";
import { noneOf, unreadOf, valueOf } from "./sources/maybe";
import type {
  BoardCard,
  BoardCards,
  InboxProjection,
  Portfolio,
  PortfolioComms,
  PortfolioCounts,
  PortfolioEscalation,
  PortfolioLane,
  PortfolioProject,
  PortfolioThread,
  Reading,
  ThreadLink,
  UnreachedScope,
} from "./interface";
import type { Known } from "./sources/maybe";

/**
 * The fold that makes three project boards and one inbox into the director's
 * one answer.
 *
 * Every function here is pure and total: it is handed the readings and returns
 * the view, so `tests/repository/test_portfolio_projection.py` drives the real
 * module over fixed payloads and can assert each rendered number against an
 * independent recount of the same cards. The reads themselves live in
 * `read/portfolio.ts`; nothing in this file knows a URL.
 *
 * Three rules hold across all of it, and each one is a place where an easier
 * number would have been a false one:
 *
 * * **A board that did not answer is never a zero.** Its project row carries
 *   `unread` with the failure's own reason, the portfolio totals count only the
 *   boards that answered, and the page says how many of how many those were.
 * * **A zero that was measured says so — and only then.** Three boards
 *   answering with no escalation is a fact about the record, and it is rendered
 *   as one. The same empty list under a board that did not answer is not that
 *   fact, so the fold keeps the two apart and names the scopes that were not
 *   reached rather than letting an empty list stand for either.
 * * **A thread belongs to a project only when a card says so.** The board card
 *   carries `inbox_thread_ids`; that recorded link is the only attribution used,
 *   and unread mail on threads no card links is counted apart rather than spread
 *   across projects or quietly dropped. A board that did not answer withholds
 *   that split rather than resolving it: its unread cards could name any thread,
 *   so *no answered board names it* is not *the record links it to nothing*.
 */

/** The word the inbox projection uses for a principal that holds no seat row. */
const UNADDRESSABLE = "unaddressable";

const UNADDRESSABLE_WHY =
  "the inbox projection resolves a recipient from the project-seat registry, and it holds no seat " +
  "for the principal this surface reads with — so no thread can be addressed here at all. This is " +
  "not an empty inbox: it is an address that does not exist.";

function isEscalated(card: BoardCard): boolean {
  return card.humanWaiting.state === "waiting";
}

function escalationOf(card: BoardCard): PortfolioEscalation | null {
  const waiting = card.humanWaiting;
  if (waiting.state !== "waiting") {
    return null;
  }
  return {
    projectKey: card.projectKey,
    ticketId: card.ticketId,
    title: card.title,
    lane: card.lane,
    priority: card.priority,
    kindKey: waiting.kind_key,
    reasonCode: waiting.reason_code,
    findingId: waiting.finding_id,
  };
}

/** Every lane, in the record's order, so a lane with no cards is still a column. */
function lanesOf(cards: readonly BoardCard[]): readonly PortfolioLane[] {
  return LANES.map((lane) => ({
    lane,
    count: cards.filter((card) => card.lane === lane).length,
  }));
}

export function countsOf(board: BoardCards): PortfolioCounts {
  return {
    lanes: lanesOf(board.cards),
    tickets: board.cards.length,
    staged: board.cards.filter((card) => card.stageKey !== null).length,
    health: board.health,
    projectionWatermark: board.projectionWatermark,
    sourceWatermark: board.sourceWatermark,
  };
}

/** One project's board reading, projected — including the reading that failed. */
function countsFor(board: Reading<BoardCards>): Known<PortfolioCounts> {
  switch (board.state) {
    case "present":
      return valueOf(countsOf(board.value));
    case "absent":
      return noneOf(`the record holds no board for this project: ${board.source.what}`);
    case "unavailable":
      return unreadOf(
        `${board.failure.reason} · ${board.failure.attempts.toString()} bounded attempts over ${board.failure.elapsedMs.toString()}ms`
      );
  }
}

function cardsOf(board: Reading<BoardCards>): readonly BoardCard[] {
  return board.state === "present" ? board.value.cards : [];
}

/**
 * What the escalation panel may claim, given which boards answered.
 *
 * Three sentences, and the empty one is where an easy answer lies: an empty
 * findings list is what boards holding none produce *and* what boards that
 * never answered produce, and only the first is a measurement. `unknown` is
 * that same emptiness carrying the scopes that make it unreadable as absence.
 */
export type EscalationSet =
  | {
      readonly known: "open";
      readonly escalations: readonly PortfolioEscalation[];
      readonly unreached: readonly UnreachedScope[];
    }
  | { readonly known: "none" }
  | { readonly known: "unknown"; readonly unreached: readonly UnreachedScope[] };

/** The panel's own decision, so no screen re-derives it from a list length. */
export function escalationsOf(portfolio: Portfolio): EscalationSet {
  if (portfolio.escalations.length > 0) {
    return { known: "open", escalations: portfolio.escalations, unreached: portfolio.unreached };
  }
  return portfolio.unreached.length === 0
    ? { known: "none" }
    : { known: "unknown", unreached: portfolio.unreached };
}

/**
 * One thread's attribution: the projects that name it, or why that is unknown.
 *
 * A thread no answered board names is `unlinked` only where every board
 * answered. While one did not, its unread cards could name any thread on this
 * list, so the row says which scope is missing instead of claiming an absence.
 */
function linkOf(projects: readonly string[], unreached: readonly UnreachedScope[]): ThreadLink {
  if (projects.length > 0) {
    return { known: "linked", projects };
  }
  return unreached.length === 0
    ? { known: "unlinked" }
    : { known: "unknown", unreached: unreached.map((scope) => scope.key) };
}

/** Thread ids the cards of one project link, deduplicated. */
function linkedThreadIds(cards: readonly BoardCard[]): ReadonlySet<string> {
  return new Set(cards.flatMap((card) => card.inboxThreadIds));
}

function unreadFor(
  inbox: Reading<InboxProjection>,
  board: Reading<BoardCards>,
  linked: ReadonlySet<string>
): Known<number> {
  if (board.state !== "present") {
    // the project's own cards are what link a thread to it; without them no
    // attribution exists, and a zero here would be an attribution, not a count
    return unreadOf("this project's board did not answer, so no thread can be attributed to it");
  }
  switch (inbox.state) {
    case "present":
      return valueOf(
        inbox.value.threads
          .filter((thread) => linked.has(thread.threadId))
          .reduce((total, thread) => total + thread.unreadCount, 0)
      );
    case "absent":
      return noneOf(`the record holds no inbox for this principal: ${inbox.source.what}`);
    case "unavailable":
      return unreadOf(inbox.failure.reason);
  }
}

/** One board reading paired with the project key it was read for. */
export interface PortfolioBoardRead {
  readonly key: string;
  readonly boardHref: string;
  readonly board: Reading<BoardCards>;
}

/**
 * Every project whose board did not answer, in the failure's own words.
 *
 * `absent` is deliberately not one of them: the record answering that it holds
 * no board for a project is knowledge — no cards, so no finding and no link to
 * miss. Only a read that did not complete leaves this page unable to say what
 * is there.
 */
function unreachedOf(boards: readonly PortfolioBoardRead[]): readonly UnreachedScope[] {
  return boards.flatMap((read) =>
    read.board.state === "unavailable" ? [{ key: read.key, reason: read.board.failure.reason }] : []
  );
}

function threadsOf(
  inbox: InboxProjection,
  byProject: readonly { readonly key: string; readonly linked: ReadonlySet<string> }[],
  unreached: readonly UnreachedScope[]
): readonly PortfolioThread[] {
  return inbox.threads.map((thread) => ({
    threadId: thread.threadId,
    otherAgent: thread.otherAgent,
    lastMessagePreview: thread.lastMessagePreview,
    lastMessageAt: thread.lastMessageAt,
    unreadCount: thread.unreadCount,
    link: linkOf(
      byProject
        .filter((project) => project.linked.has(thread.threadId))
        .map((project) => project.key),
      unreached
    ),
    promotedTicketId: thread.promotedTicketId,
  }));
}

/**
 * Unread mail on threads the record links to no project — withheld entirely
 * while a board did not answer. Under a partial read every unmatched thread is
 * `unknown`, so this number could only come out as zero, and a zero here reads
 * as a split that was measured.
 */
function unlinkedOf(
  threads: readonly PortfolioThread[],
  unreached: readonly UnreachedScope[]
): Known<number> {
  if (unreached.length > 0) {
    return unreadOf(
      `${unreached.map((scope) => scope.key).join(", ")} did not answer, so no thread here can ` +
        "be called unlinked: a card on a board this read never reached could name any of them"
    );
  }
  return valueOf(
    threads
      .filter((thread) => thread.link.known === "unlinked")
      .reduce((total, thread) => total + thread.unreadCount, 0)
  );
}

function commsOf(
  inbox: Reading<InboxProjection>,
  byProject: readonly { readonly key: string; readonly linked: ReadonlySet<string> }[],
  unreached: readonly UnreachedScope[]
): Known<PortfolioComms> {
  switch (inbox.state) {
    case "present": {
      const threads = threadsOf(inbox.value, byProject, unreached);
      const addressable = inbox.value.recipient !== UNADDRESSABLE;
      return valueOf({
        recipient: inbox.value.recipient,
        addressable,
        unaddressableWhy: addressable ? null : UNADDRESSABLE_WHY,
        threads,
        totalUnread: inbox.value.totalUnread,
        unlinkedUnread: unlinkedOf(threads, unreached),
      });
    }
    case "absent":
      return noneOf(`the record holds no inbox for this principal: ${inbox.source.what}`);
    case "unavailable":
      return unreadOf(
        `${inbox.failure.reason} · ${inbox.failure.attempts.toString()} bounded attempts over ${inbox.failure.elapsedMs.toString()}ms`
      );
  }
}

/**
 * The portfolio, folded from one board reading per configured project and one
 * inbox reading.
 *
 * The result is always `present`: reaching none of the four sources is itself
 * an answer this screen can render honestly — three rows saying `not reached`
 * and a total saying `0 of 3 answered` is the truth, while an `unavailable`
 * page would hide which project failed and how.
 */
export function portfolioOf(
  boards: readonly PortfolioBoardRead[],
  inbox: Reading<InboxProjection>,
  observedAt: string
): Portfolio {
  const linkedByProject = boards.map((read) => ({
    key: read.key,
    linked: linkedThreadIds(cardsOf(read.board)),
  }));
  const unreached = unreachedOf(boards);
  const projects: readonly PortfolioProject[] = boards.map((read, index) => ({
    key: read.key,
    counts: countsFor(read.board),
    escalations: cardsOf(read.board)
      .filter(isEscalated)
      .flatMap((card) => {
        const escalation = escalationOf(card);
        return escalation === null ? [] : [escalation];
      }),
    unread: unreadFor(inbox, read.board, linkedByProject[index]?.linked ?? new Set<string>()),
    boardHref: read.boardHref,
  }));
  const answeredCards = boards.flatMap((read) => cardsOf(read.board));
  return {
    projects,
    laneTotals: lanesOf(answeredCards),
    tickets: answeredCards.length,
    staged: answeredCards.filter((card) => card.stageKey !== null).length,
    escalations: projects.flatMap((project) => project.escalations),
    comms: commsOf(inbox, linkedByProject, unreached),
    answered: boards.filter((read) => read.board.state === "present").length,
    considered: boards.length,
    unreached,
    observedAt,
  };
}
