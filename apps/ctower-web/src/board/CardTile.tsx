import type { ReactElement } from "react";
import type { BoardCard } from "@ctower/client";
import { cn } from "../ui/cn";
import { Mark } from "../ui/marks";
import { Chip, Mono } from "../ui/primitives";

/**
 * One card, and every fact on it is one the record answered with.
 *
 * Three rules do the work here. A mark is drawn only where a recorded fact
 * earns it — `⏸` for a blocker the record opened, `⚠` for a finding that is
 * waiting on a person — and a card with neither draws neither rather than
 * borrowing a neighbour's glyph. The stage is the card's own `stage_label`, so
 * a card that declares no workflow position shows none instead of being placed
 * at an invented one. And amber is spent once, on `P0`, because a priority
 * ramp where every level is coloured says nothing about any of them.
 */
/**
 * The card the detail panel came from, so closing the panel can put the
 * keyboard back where it was. The panel is opened from state rather than from a
 * Radix trigger, so nothing restores focus unless this says where to.
 */
export function cardElementId(ticketId: string): string {
  return `board-card-${ticketId}`;
}

export function CardTile({
  card,
  selected,
  onOpen,
}: {
  readonly card: BoardCard;
  readonly selected: boolean;
  readonly onOpen: (card: BoardCard) => void;
}): ReactElement {
  const waiting = card.human_waiting.state === "waiting";

  return (
    <button
      type="button"
      id={cardElementId(card.ticket_id)}
      aria-pressed={selected}
      onClick={(): void => {
        onOpen(card);
      }}
      className={cn(
        "block w-full cursor-pointer rounded-md border bg-card p-2.5 text-left",
        "border-l-2 hover:bg-raised",
        selected ? "border-line border-l-amber bg-raised" : "border-line border-l-line"
      )}
    >
      <div className="flex items-center gap-1.5">
        {card.display_key === null ? (
          <span className="min-w-0 flex-1" />
        ) : (
          <Mono className="min-w-0 flex-1 truncate text-muted">{card.display_key}</Mono>
        )}
        <Chip tone={card.priority === "P0" ? "amber" : "neutral"}>{card.priority}</Chip>
      </div>

      <p className="mt-1.5 mb-0 line-clamp-3 text-sm leading-snug">{card.title}</p>

      {card.stage_label === null && !waiting && card.blocker_reason === null ? null : (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {card.stage_label === null ? null : <Chip>{card.stage_label}</Chip>}
          {waiting ? (
            <span className="inline-flex items-center text-2xs text-muted">
              <Mark name="warn" />
              waiting on a person
            </span>
          ) : null}
        </div>
      )}

      {card.blocker_reason === null ? null : (
        <p className="mt-1.5 mb-0 flex items-start text-2xs text-muted">
          <Mark name="parked" className="mt-px" />
          <span className="min-w-0 flex-1 truncate" title={card.blocker_reason}>
            {card.blocker_reason}
          </span>
        </p>
      )}
    </button>
  );
}
