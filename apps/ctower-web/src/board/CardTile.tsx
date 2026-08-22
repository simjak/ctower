import type { ReactElement } from "react";
import type { BoardCard } from "@ctower/client";
import { cn } from "../ui/cn";
import { Mark } from "../ui/marks";
import { Chip, Mono } from "../ui/primitives";

/**
 * One ticket, at the density a column allows.
 *
 * A card draws only what the projection recorded. `display_key` is null until a
 * project component gives the tenant a prefix, so a card without one shows no
 * key rather than a placeholder; a stage is drawn only where the ticket declares
 * one; and the warning mark appears only where `human_waiting` says a person is
 * actually waiting, never as a guess about a lane.
 */
export function CardTile({
  card,
  selected,
  onOpen,
}: {
  readonly card: BoardCard;
  readonly selected: boolean;
  readonly onOpen: () => void;
}): ReactElement {
  const waiting = card.human_waiting.state === "waiting";

  return (
    <li>
      <button
        type="button"
        aria-current={selected}
        onClick={onOpen}
        className={cn(
          "w-full cursor-pointer rounded-sm border p-2.5 text-left",
          selected ? "border-amber bg-raised" : "border-line bg-card hover:bg-raised"
        )}
      >
        <div className="flex items-center gap-2">
          {card.display_key === null ? null : (
            // The key is one token and never breaks: a `CTW-11` split over two
            // lines is a key nobody can read back over a terminal.
            <Mono className="shrink-0 whitespace-nowrap text-muted">{card.display_key}</Mono>
          )}
          <span className="flex-1" />
          {waiting ? <Mark name="warn" /> : null}
          <Chip tone={card.priority === "P0" ? "amber" : "neutral"}>{card.priority}</Chip>
        </div>
        <p className="m-0 mt-1 text-sm leading-snug">{card.title}</p>
        {card.stage_label === null ? null : (
          <Mono className="mt-1.5 block text-muted">{card.stage_label}</Mono>
        )}
      </button>
    </li>
  );
}
