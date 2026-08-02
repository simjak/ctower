import { recordAdapter } from "./adapter";
import { mapReading } from "./reading";
import type { Reading } from "./interface";

/**
 * The section link `Ticket` needs one ticket to open on. The choice is the most
 * recently created ticket the record holds — a recorded fact and a stable rule,
 * not a hand-picked example.
 *
 * The answer is a `Reading`: a board read that did not reach the record stays
 * unavailable rather than becoming "there are no tickets".
 */
export async function newestTicketId(): Promise<Reading<string>> {
  return mapReading(await recordAdapter.board(), (snapshot): Reading<string> => {
    const created = snapshot.entries.flatMap((entry) =>
      entry.ticket.state === "present"
        ? [{ ticketId: entry.card.ticketId, createdAt: entry.ticket.value.createdAt }]
        : []
    );
    const newest = [...created].sort((left, right) =>
      right.createdAt.localeCompare(left.createdAt)
    )[0];
    const fallback = snapshot.entries[0]?.card.ticketId;
    const chosen = newest?.ticketId ?? fallback;
    return chosen === undefined
      ? {
          state: "absent",
          source: { lands: "#186", what: "any ticket on the board projection" },
        }
      : { state: "present", value: chosen };
  });
}
