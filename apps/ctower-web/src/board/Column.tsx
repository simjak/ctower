import type { ReactElement } from "react";
import type { BoardCard } from "@ctower/client";
import { CardTile } from "./CardTile";
import type { Column as ColumnFacts } from "./lanes";

/**
 * One lane, drawn as a column.
 *
 * The header is the table header this system already fixes — 12px, muted, the
 * count tabular — because a board column head and a table head are the same
 * job. It carries no mark: `Backlog` and `Ready` are recorded lanes, not
 * recorded states in the shared glyph vocabulary, and a column that borrowed
 * `○` for one of them would be asserting something the record never said.
 *
 * An empty lane keeps its column. A board where the columns move as work moves
 * is a board an operator cannot read at a glance, and an empty lane is a fact
 * worth seeing.
 */
export function Column({
  column,
  selectedId,
  onOpen,
}: {
  readonly column: ColumnFacts;
  readonly selectedId: string | null;
  readonly onOpen: (card: BoardCard) => void;
}): ReactElement {
  return (
    <section aria-label={column.label} className="flex min-w-0 flex-col">
      {/* The count sits against its own label, not against the column's right
          edge: with no rule between columns, a right-aligned number reads as
          though it belongs to the heading beside it. */}
      <header className="flex items-baseline gap-1.5 border-b border-line pb-1.5">
        <h2 className="m-0 min-w-0 truncate text-2xs leading-none font-medium text-muted">
          {column.label}
        </h2>
        <span className="text-2xs text-muted">{column.cards.length}</span>
      </header>
      {/* The stack scrolls inside the column rather than the page, so the six
          heads stay put while a long lane is read. */}
      <div className="mt-2 flex max-h-[calc(100dvh-210px)] flex-col gap-2 overflow-y-auto pr-1">
        {column.cards.map((card) => (
          <CardTile
            key={card.ticket_id}
            card={card}
            selected={card.ticket_id === selectedId}
            onOpen={onOpen}
          />
        ))}
      </div>
    </section>
  );
}
