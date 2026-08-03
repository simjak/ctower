import { NO_BOARD_ROW_HERE } from "./futureSources";
import { mapReading } from "./reading";
import type { BoardCard, BoardEntry, BoardSnapshot, Reading } from "./interface";

/**
 * Projections over the board's per-card ticket readings.
 *
 * These live in the read layer, not in a surface, because they are the only
 * place outside `frame/Declared.tsx` that inspects a reading's state — and they
 * turn it into a typed summary a screen can render without ever seeing a
 * `Reading` it might flatten.
 */

/**
 * The recorded source kind, or `null` when this card's ticket read did not
 * produce one. `null` means "not resolvable", never "no source recorded".
 */
export function sourceKindOf(entry: BoardEntry): string | null {
  return entry.ticket.state === "present" ? entry.ticket.value.source.kind : null;
}

/** Cards whose source could not be resolved, with the first reason observed. */
export interface UnresolvedSources {
  readonly count: number;
  readonly unreached: number;
  readonly reason: string | null;
}

export function unresolvedSources(entries: readonly BoardEntry[]): UnresolvedSources {
  const unresolved = entries.filter((entry) => entry.ticket.state !== "present");
  const reasons = entries.flatMap((entry) =>
    entry.ticket.state === "unavailable" ? [entry.ticket.failure.reason] : []
  );
  return {
    count: unresolved.length,
    unreached: reasons.length,
    reason: reasons[0] ?? null,
  };
}

/**
 * This ticket's board row, as a reading.
 *
 * A board read that did not answer stays unavailable rather than becoming "no
 * lane recorded": the ticket screen must not imply the projection holds nothing
 * for this ticket when the truth is that the projection was not reached.
 */
export function cardFor(board: Reading<BoardSnapshot>, ticketId: string): Reading<BoardCard> {
  return mapReading(board, (snapshot): Reading<BoardCard> => {
    const found = snapshot.entries.find((entry) => entry.card.ticketId === ticketId);
    return found === undefined
      ? { state: "absent", source: NO_BOARD_ROW_HERE }
      : { state: "present", value: found.card };
  });
}
