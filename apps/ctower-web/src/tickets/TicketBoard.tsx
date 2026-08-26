import type { ReactElement } from "react";
import type { BoardCard, BoardLane } from "@ctower/client";
import { Chip } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { LANES, laneWord, numberWord, priorityWord } from "./words";

/**
 * The same tickets, as columns.
 *
 * Six columns, because `BoardLane` is closed at six. The operator's own kanban
 * reference draws a seventh for cancelled work and this one does not: the
 * record keeps no such lane, so a `CANCELLED` column is a column nothing could
 * ever arrive in.
 *
 * This is a second reading of one `getBoard` answer, not a second read — the
 * same feed `ctowerctl board query` serves, so the console and the terminal
 * cannot disagree about what is on this project. That is also why the toggle
 * beside it is a switch rather than a destination that asks again.
 *
 * Nothing here moves a card. `moveTicket` exists and this screen does not draw
 * it: where a ticket goes next is the ticket's own page, which says what the
 * move means before it makes one.
 */
export function TicketBoard({
  cards,
  onOpen,
}: {
  readonly cards: readonly BoardCard[];
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return (
    <div className="grid grid-cols-6 gap-3">
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

/**
 * One lane, drawn as a column.
 *
 * An empty lane keeps its column: a board whose columns come and go as work
 * moves is one the eye has to re-learn every morning, and a lane with nothing
 * in it is a fact worth seeing. The head carries no mark — a lane is a place
 * work sits, not one of the six recorded states the shared glyphs stand for.
 */
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
    <section aria-label={laneWord(lane)} className="min-w-0">
      {/* The count sits against its own label rather than at the column's right
          edge: with no rule between columns, a right-aligned number reads as
          though it belongs to the heading beside it. */}
      <header className="mb-3 flex items-baseline gap-1.5">
        <h2 className="m-0 min-w-0 truncate text-2xs tracking-[0.08em] text-muted uppercase">
          {laneWord(lane)}
        </h2>
        <span className="text-2xs text-muted">{cards.length}</span>
      </header>
      <div className="flex flex-col gap-2.5">
        {cards.map((card) => (
          <Tile key={card.ticket_id} card={card} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}

/**
 * One card, and every fact on it is one a person would say out loud.
 *
 * The reference's card carries a number, a title and a face. Two of those are
 * the record's own and the third is not drawn at all: `assignee_id` and
 * `custodian_id` are identifiers, and no read this console can make turns one
 * into a name, so a face here would be an invented value on a screen whose
 * whole claim is that nothing on it is.
 *
 * Nothing is added for balance. A stage is drawn when the card declares one,
 * `Urgent` when the record carries the one priority it treats differently, the
 * shared `⚠` when a person is being waited on, and the blocker in the words
 * somebody wrote. A card with none of those has nothing to say and says
 * nothing.
 */
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
      className="block w-full cursor-pointer rounded-md border border-line bg-card p-3 text-left hover:bg-raised"
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-2xs text-muted">
          {numberWord(card.display_key)}
        </span>
        {/* The one amber fill on a card, and it is a fill carrying `--on-amber`
            rather than an amber word. Urgent is the only priority the record
            treats as authority, so it is the only one that renders at all. */}
        {card.priority === "P0" ? (
          <Chip className="border-amber bg-amber font-semibold text-on-amber">
            {priorityWord("P0")}
          </Chip>
        ) : null}
      </div>

      <p className="mt-1.5 mb-0 line-clamp-3 text-sm leading-snug">{card.title}</p>

      <Foot card={card} />

      {/* Why it is stopped, in the words a person wrote. No glyph in front of
          it: the sentence is already the whole fact, and the column it sits in
          has said Stuck at the top. */}
      {card.blocker_reason === null ? null : (
        <p className="mt-2 mb-0 text-2xs text-muted">{card.blocker_reason}</p>
      )}
    </button>
  );
}

/** The line under the title: where it stands, and whether it wants a person. */
function Foot({ card }: { readonly card: BoardCard }): ReactElement | null {
  const waiting = card.human_waiting.state === "waiting";
  if (card.stage_label === null && !waiting) {
    return null;
  }
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-2">
      {card.stage_label === null ? null : <Chip>{card.stage_label}</Chip>}
      {waiting ? (
        <span className="inline-flex items-center text-2xs text-amber-ink">
          <Mark name="warn" />
          Needs you
        </span>
      ) : null}
    </div>
  );
}
