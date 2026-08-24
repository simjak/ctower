import type { ReactElement } from "react";
import { Chip } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import type { MockCard } from "./fixtures";

/**
 * One card, and every fact on it is one a person would say out loud.
 *
 * The reference's card carries three things: the number, the title, and a face.
 * Two of them are the record's own. The third is drawn only when this bench is
 * asked to show his reference as he drew it — see `face` — because the record
 * answers who with an identifier and no read turns one into a name.
 *
 * Nothing else is added for balance. A stage is drawn when the card declares
 * one, `Urgent` when the record carries the one priority it treats differently,
 * the CLI's own `⚠` when a person is being waited on, and the blocker in the
 * words somebody wrote. A card with none of those is a card with nothing to
 * say, and it says nothing.
 */
export function CardTile({
  card,
  face,
}: {
  readonly card: MockCard;
  /** Whether to draw the name his reference puts on a card. */
  readonly face: boolean;
}): ReactElement {
  return (
    <button
      type="button"
      className="block w-full cursor-pointer rounded-md border border-line bg-card p-3 text-left hover:bg-raised"
    >
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-2xs text-muted">
          {card.key ?? "no number yet"}
        </span>
        {card.priority === "P0" ? (
          <Chip className="border-amber bg-amber font-semibold text-on-amber">Urgent</Chip>
        ) : null}
      </div>

      <p className="mt-1.5 mb-0 line-clamp-3 text-sm leading-snug">{card.title}</p>

      <Foot card={card} face={face} />

      {/* Why it is stopped, in the words a person wrote. No glyph in front of
          it: the sentence is already the whole fact, and the column it sits in
          has said `Stuck` at the top. */}
      {card.blocked === null ? null : (
        <p className="mt-2 mb-0 text-2xs text-muted">{card.blocked}</p>
      )}
    </button>
  );
}

/** The line under the title: where it stands, who has it, and nothing invented. */
function Foot({
  card,
  face,
}: {
  readonly card: MockCard;
  readonly face: boolean;
}): ReactElement | null {
  const nothing = card.stage === null && !card.waiting;
  if (nothing && !face) {
    return null;
  }
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-2">
      {card.stage === null ? null : <Chip>{card.stage}</Chip>}
      {card.waiting ? (
        <span className="inline-flex items-center text-2xs text-amber-ink">
          <Mark name="warn" />
          Needs you
        </span>
      ) : null}
      {face ? <Face name={card.face} /> : null}
    </div>
  );
}

/**
 * The name his reference draws, and the only invented value on this bench.
 * It sits at the card's right edge, where his own board puts the avatar.
 */
function Face({ name }: { readonly name: string }): ReactElement {
  return (
    <span className="ml-auto inline-flex items-center gap-1.5 text-2xs text-muted">
      <span
        aria-hidden
        className="grid size-5 shrink-0 place-content-center rounded-full bg-raised text-[10px] font-semibold"
      >
        {name.slice(0, 1)}
      </span>
      {name}
    </span>
  );
}
