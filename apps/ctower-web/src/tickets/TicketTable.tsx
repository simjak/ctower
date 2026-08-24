import type { ReactElement } from "react";
import type { BoardCard } from "@ctower/client";
import { Mono } from "../ui/primitives";
import { laneWord, Marks, PriorityChip } from "./facts";

/**
 * The tickets, as a table.
 *
 * `DESIGN.md`: 13.5px, a 12px muted head, row borders only, no zebra. Every
 * column is a fact the read answered with — there is no derived column and no
 * count this page worked out for itself.
 *
 * The rows keep the board's order. The projection serves its cards
 * `ORDER BY ticket_id` (the record's own position for a ticket), and a client
 * that re-sorted them — by lane, or by the number in a display key — would be
 * overruling that answer with a rule of its own.
 *
 * A row is opened from the button in its key cell. The row is clickable too,
 * because an operator aims at the row, but the button is the one focusable
 * thing in it, so a keyboard walks the list a row at a time.
 */

export function TicketTable({
  cards,
  onOpen,
}: {
  readonly cards: readonly BoardCard[];
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-line text-left text-2xs text-muted">
          <th scope="col" className="py-1.5 pr-3 font-normal">
            Ticket
          </th>
          {/* The marks have a column of their own so that a title on a row
              that earned one still begins where every other title begins. */}
          <th scope="col" className="w-9 py-1.5 font-normal">
            <span className="sr-only">Attention</span>
          </th>
          <th scope="col" className="py-1.5 pr-3 font-normal">
            Title
          </th>
          <th scope="col" className="py-1.5 pr-3 font-normal">
            Priority
          </th>
          <th scope="col" className="py-1.5 pr-3 font-normal">
            Standing
          </th>
          <th scope="col" className="py-1.5 font-normal">
            Stage
          </th>
        </tr>
      </thead>
      <tbody>
        {cards.map((card) => (
          <Row key={card.ticket_id} card={card} onOpen={onOpen} />
        ))}
      </tbody>
    </table>
  );
}

function Row({
  card,
  onOpen,
}: {
  readonly card: BoardCard;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return (
    <tr
      className="cursor-pointer border-b border-line hover:bg-raised"
      onClick={(): void => {
        onOpen(card.ticket_id);
      }}
    >
      <td className="py-1.5 pr-3 align-top whitespace-nowrap">
        <button
          type="button"
          className="cursor-pointer rounded-sm text-left"
          onClick={(event): void => {
            event.stopPropagation();
            onOpen(card.ticket_id);
          }}
        >
          {/* The ticket's own number, the one a person says out loud. A card
              the record has not numbered yet says so: its identifier is a
              machine one and putting it here would put a uuid on the screen. */}
          {card.display_key === null ? (
            <span className="text-muted">Unnumbered</span>
          ) : (
            <Mono className="text-fg">{card.display_key}</Mono>
          )}
          <span className="sr-only"> — {card.title}</span>
        </button>
      </td>
      <td className="w-9 py-1.5 align-top whitespace-nowrap">
        <Marks card={card} />
      </td>
      <td className="py-1.5 pr-3 align-top">{card.title}</td>
      <td className="py-1.5 pr-3 align-top">
        <PriorityChip priority={card.priority} />
      </td>
      <td className="py-1.5 pr-3 align-top whitespace-nowrap">{laneWord(card.lane)}</td>
      <td className="py-1.5 align-top whitespace-nowrap">
        {/* No workflow has told the record where this ticket stands. An em
            dash says so; borrowing the lane's word would invent a stage. */}
        {card.stage_label ?? <span className="text-muted">—</span>}
      </td>
    </tr>
  );
}
