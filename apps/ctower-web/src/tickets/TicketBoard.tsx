import type { ReactElement } from "react";
import type { BoardCard, BoardLane } from "@ctower/client";
import { Chip } from "../ui/primitives";
import { Marks } from "./facts";
import { LANES, laneWord, numberWord, priorityWord } from "./words";

/**
 * The same tickets, as columns.
 *
 * Six columns, because `BoardLane` is closed at six. The reference draws a
 * seventh for cancelled work and this one does not: the record keeps no such
 * lane, and a column that can never fill is a promise the console cannot keep.
 *
 * This is a second reading of the list's own answer, not a second read. One
 * `getBoard` feeds both, so the two views cannot disagree about what is on the
 * project — which is the whole reason the toggle sits beside the list rather
 * than being a destination that asks again.
 */
export function TicketBoard({
  cards,
  onOpen,
}: {
  readonly cards: readonly BoardCard[];
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
      {LANES.map((lane) => (
        <Column
          key={lane}
          lane={lane}
          cards={cards.filter((card) => card.lane === lane)}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}

function Column({
  lane,
  cards,
  onOpen,
}: {
  readonly lane: BoardLane;
  readonly cards: readonly BoardCard[];
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return (
    <section className="min-w-0">
      <header className="mb-3 flex items-baseline gap-2">
        <h2 className="m-0 text-2xs font-medium tracking-[0.09em] text-muted uppercase">
          {laneWord(lane)}
        </h2>
        <span className="ml-auto text-2xs text-muted">{cards.length}</span>
      </header>
      {cards.map((card) => (
        <Tile key={card.ticket_id} card={card} onOpen={onOpen} />
      ))}
    </section>
  );
}

function Tile({
  card,
  onOpen,
}: {
  readonly card: BoardCard;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={(): void => {
        onOpen(card.ticket_id);
      }}
      className="mb-2.5 block w-full cursor-pointer rounded-md border border-line bg-card p-3 text-left hover:bg-raised"
    >
      <span className="flex items-center gap-1.5 text-2xs text-muted">
        <Marks card={card} />
        {numberWord(card.display_key)}
      </span>
      <span className="mt-1 block text-sm">{card.title}</span>
      {card.priority === "P0" ? (
        <span className="mt-2 block">
          <Chip tone="amber">{priorityWord("P0")}</Chip>
        </span>
      ) : null}
    </button>
  );
}
