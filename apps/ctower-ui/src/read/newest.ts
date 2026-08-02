import type { BoardEntry, BoardSnapshot } from "./interface";

/**
 * The section links `Ticket` and `Feed` need one ticket to open on. The choice
 * is the most recently created ticket the record holds — a recorded fact and a
 * stable rule, not a hand-picked example.
 */
export function newestTicketId(snapshot: BoardSnapshot): string | null {
  const dated = snapshot.entries.filter(
    (entry): entry is BoardEntry & { readonly ticket: NonNullable<BoardEntry["ticket"]> } =>
      entry.ticket !== null
  );
  const newest = [...dated].sort((left, right) =>
    right.ticket.createdAt.localeCompare(left.ticket.createdAt)
  )[0];
  return newest?.card.ticketId ?? snapshot.entries[0]?.card.ticketId ?? null;
}
