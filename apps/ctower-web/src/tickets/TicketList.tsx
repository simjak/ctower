import type { ReactElement } from "react";
import type { BoardCard } from "@ctower/client";
import { Chip } from "../ui/primitives";
import { Marks } from "./facts";
import type { Raisings } from "./raised";
import { ageWords, bandWord, laneTone, laneWord, numberWord, priorityWord } from "./words";

/**
 * The tickets on this project, as the list you walk down.
 *
 * The frozen spec's row is five things and no more: whether it wants attention,
 * the number a person says out loud, what it is, where it stands, and how long
 * ago it was raised. Everything the reference draws beyond that is either a
 * fact the record does not keep or a machine word the operator ruled off this
 * surface — a lane enum, a priority code, a stamp.
 *
 * **The attention column is the CLI's own glyphs.** `DESIGN.md` makes the six
 * marks shared with `ctowerctl` non-negotiable, so a blocker draws `⏸` and a
 * person being waited on draws `⚠`, and a ticket with neither draws nothing.
 * The reference's plain dot would have been a seventh mark meaning two things.
 *
 * **Urgent is the one priority that renders.** It is the only one the record
 * treats as authority rather than as an opinion, so it is the only one worth a
 * word on a row somebody is scanning.
 *
 * The order is the board's. The projection serves its cards in the record's own
 * position and re-sorting them here would overrule that answer; the bands are a
 * heading drawn between rows, never a reordering of them.
 */
export function TicketList({
  cards,
  raisings,
  now,
  onOpen,
}: {
  readonly cards: readonly BoardCard[];
  /** When each of these was raised, as far as the project's feed answered. */
  readonly raisings: Raisings;
  /** The instant this screen is reading against, so every age agrees. */
  readonly now: number;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  let band: string | null = null;
  return (
    <ul className="m-0 list-none p-0">
      {cards.map((card) => {
        const raised = raisings.at.get(card.ticket_id) ?? null;
        const here = raised === null ? "Undated" : bandWord(raised, now);
        const opens = here !== band;
        band = here;
        return (
          <li key={card.ticket_id}>
            {opens ? <Band word={here} /> : null}
            <Row card={card} raised={raised} now={now} onOpen={onOpen} />
          </li>
        );
      })}
    </ul>
  );
}

/**
 * A heading between rows. `Undated` is not a time — it is what a list says
 * about a ticket whose raising was not in the pages the feed answered with,
 * rather than quietly filing it under the oldest band.
 */
function Band({ word }: { readonly word: string }): ReactElement {
  return (
    <div className="mt-6 mb-1 flex items-center gap-3 first:mt-0">
      <span className="text-2xs tracking-[0.09em] text-muted uppercase">{word}</span>
      <span className="h-px flex-1 bg-line" />
    </div>
  );
}

function Row({
  card,
  raised,
  now,
  onOpen,
}: {
  readonly card: BoardCard;
  readonly raised: string | null;
  readonly now: number;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={(): void => {
        onOpen(card.ticket_id);
      }}
      className="flex w-full cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 text-left hover:bg-raised"
    >
      <span className="w-5 shrink-0">
        <Marks card={card} />
      </span>
      <span className="w-20 shrink-0 text-xs text-muted">{numberWord(card.display_key)}</span>
      <span className="min-w-0 flex-1 truncate text-md">{card.title}</span>
      {card.priority === "P0" ? <Chip tone="amber">{priorityWord("P0")}</Chip> : null}
      <Chip tone={laneTone(card.lane)}>{laneWord(card.lane)}</Chip>
      <span className="w-20 shrink-0 text-right text-xs text-muted">
        {raised === null ? "" : ageWords(raised, now)}
      </span>
    </button>
  );
}
