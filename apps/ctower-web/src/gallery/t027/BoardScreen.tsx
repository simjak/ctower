import { Columns3, LayoutList, Plus } from "lucide-react";
import type { ReactElement } from "react";
import type { BoardLane } from "@ctower/client";
import { Button, Input, Mono } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import { laneWord } from "../../tickets/facts";
import { LANES } from "../../board/lanes";
import { TICKETS } from "./fixtures";
import type { MockTicket } from "./fixtures";

/**
 * The same tickets, read as columns.
 *
 * Six columns, and they are the record's own closed set of lanes in the order
 * work moves through them. The reference has seven — its seventh is CANCELLED,
 * and ctower records no such lane, so drawing one would give the operator a
 * column nothing can ever arrive in.
 *
 * A card carries what the reference's card carries, minus the face: the number,
 * the title, and the marks it has actually earned. Nothing here is grouped by a
 * guess — a card is in a column because the record answered with that lane.
 */
export function BoardScreen({ onOpen }: { readonly onOpen: () => void }): ReactElement {
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onOpen}>
          <Plus /> New ticket
        </Button>
        <Input
          defaultValue=""
          placeholder="Search these tickets"
          aria-label="Search these tickets"
          className="h-7 w-56 text-xs"
        />
        <span className="flex-1" />
        <Button variant="quiet" size="sm" aria-label="List">
          <LayoutList />
        </Button>
        <Button variant="quiet" size="sm" aria-label="Board" aria-pressed className="text-fg">
          <Columns3 />
        </Button>
      </div>

      <div className="grid grid-cols-6 gap-3">
        {LANES.map((lane) => (
          <Column key={lane} lane={lane} onOpen={onOpen} />
        ))}
      </div>
    </>
  );
}

function Column({
  lane,
  onOpen,
}: {
  readonly lane: BoardLane;
  readonly onOpen: () => void;
}): ReactElement {
  const held = TICKETS.filter((ticket) => ticket.lane === lane);
  return (
    <section className="min-w-0">
      <header className="mb-2 flex items-baseline gap-2 border-b border-line pb-1.5">
        <h2 className="m-0 min-w-0 flex-1 truncate text-2xs tracking-[0.06em] text-muted uppercase">
          {laneWord(lane)}
        </h2>
        <span className="text-2xs text-muted">{held.length}</span>
      </header>
      <div className="space-y-2">
        {held.map((ticket) => (
          <Tile key={ticket.key ?? ticket.title} ticket={ticket} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}

function Tile({
  ticket,
  onOpen,
}: {
  readonly ticket: MockTicket;
  readonly onOpen: () => void;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full cursor-pointer rounded-md border border-line bg-card p-2.5 text-left hover:bg-raised"
    >
      <div className="flex items-center gap-1.5">
        {ticket.key === null ? (
          <span className="text-2xs text-muted">Unnumbered</span>
        ) : (
          <Mono className="text-muted">{ticket.key}</Mono>
        )}
        <span className="flex-1" />
        {ticket.blocked === null ? null : <Mark name="parked" />}
        {ticket.waiting ? <Mark name="warn" /> : null}
        {ticket.priority === "P0" ? <span className="text-2xs text-amber-ink">P0</span> : null}
      </div>
      <p className="mt-1 mb-0 text-sm">{ticket.title}</p>
      {ticket.stage === null ? null : (
        <p className="mt-1.5 mb-0 text-2xs text-muted">{ticket.stage}</p>
      )}
    </button>
  );
}
