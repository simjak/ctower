import { recordAdapter } from "./adapter";
import { mapReading } from "./reading";
import { rankStrictly } from "./selectors";
import type { Candidate, Ranked } from "./selectors";
import type { BoardEntry, Reading } from "./interface";

/**
 * The section link `Ticket` needs one ticket to open on: the most recently
 * created ticket the record holds.
 *
 * The creation time comes from a per-card join, and a join can fail on its own.
 * That superlative therefore cannot be made from a partial fan-out — a ticket
 * whose creation time was not read could be the newest — and the result is a
 * redirect, which has nowhere to carry a caveat. So this ranks *strictly*: any
 * unread candidate makes the answer `unavailable`, and the screen says which
 * read failed instead of redirecting somewhere it cannot justify.
 *
 * Round-2 review found the previous version discarding unread joins and, when
 * every join failed, falling back to the first board card — a known answer
 * fabricated from a creation time nobody read.
 */
import { NO_TICKET_ON_BOARD } from "./futureSources";

export function newestCandidates(entries: readonly BoardEntry[]): readonly Candidate<string>[] {
  return entries.map((entry) => ({
    // the join's value is not needed, only whether it answered — the card
    // already carries the id, and the join carries the creation time we rank by
    reading: mapReading(entry.ticket, (): Reading<string> => ({
      state: "present",
      value: entry.card.ticketId,
    })),
    orderBy: entry.ticket.state === "present" ? entry.ticket.value.createdAt : "",
  }));
}

export async function newestTicketId(projectKey: string): Promise<Reading<Ranked<string>>> {
  return mapReading(await recordAdapter.board(projectKey), (snapshot) =>
    rankStrictly(newestCandidates(snapshot.entries), NO_TICKET_ON_BOARD)
  );
}
