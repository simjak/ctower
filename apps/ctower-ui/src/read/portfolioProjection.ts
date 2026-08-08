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
 * * **A zero that was measured says so.** Three boards answering with no
 *   escalation is a fact about the record, and it is rendered as one — never as
 *   an empty list that could equally mean nobody looked.
 * * **A thread belongs to a project only when a card says so.** The board card
 *   carries `inbox_thread_ids`; that recorded link is the only attribution used,
 *   and unread mail on threads no card links is counted apart rather than spread
 *   across projects or quietly dropped.
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

function failureOf(board: Reading<BoardCards>): string | null {
  return board.state === "unavailable" ? board.failure.reason : null;
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

function threadsOf(
  inbox: InboxProjection,
  byProject: readonly { readonly key: string; readonly linked: ReadonlySet<string> }[]
): readonly PortfolioThread[] {
  return inbox.threads.map((thread) => ({
    threadId: thread.threadId,
    otherAgent: thread.otherAgent,
    lastMessagePreview: thread.lastMessagePreview,
    lastMessageAt: thread.lastMessageAt,
    unreadCount: thread.unreadCount,
    projects: byProject
      .filter((project) => project.linked.has(thread.threadId))
      .map((project) => project.key),
    promotedTicketId: thread.promotedTicketId,
  }));
}

function commsOf(
  inbox: Reading<InboxProjection>,
  byProject: readonly { readonly key: string; readonly linked: ReadonlySet<string> }[]
): Known<PortfolioComms> {
  switch (inbox.state) {
    case "present": {
      const threads = threadsOf(inbox.value, byProject);
      const addressable = inbox.value.recipient !== UNADDRESSABLE;
      return valueOf({
        recipient: inbox.value.recipient,
        addressable,
        unaddressableWhy: addressable ? null : UNADDRESSABLE_WHY,
        threads,
        totalUnread: inbox.value.totalUnread,
        unlinkedUnread: threads
          .filter((thread) => thread.projects.length === 0)
          .reduce((total, thread) => total + thread.unreadCount, 0),
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
    comms: commsOf(inbox, linkedByProject),
    answered: boards.filter((read) => read.board.state === "present").length,
    considered: boards.length,
    reason: boards.map((read) => failureOf(read.board)).find((reason) => reason !== null) ?? null,
    observedAt,
  };
}
