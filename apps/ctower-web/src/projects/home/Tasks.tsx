import { useState } from "react";
import { Columns3, Filter, Group, LayoutList, ListTree, Plus, SortAsc } from "lucide-react";
import type { ReactElement } from "react";
import type { BoardCard } from "@ctower/client";
import { Button, Input } from "../../ui/primitives";
import { TicketTable } from "../../tickets/TicketTable";
import { useBoard } from "../../tickets/reads";
import { Asking, Malformed, Refused, Unreachable } from "../../wizard/states";
import { Inert } from "../Inert";
import type { ProjectFacts } from "../read";

/**
 * The project's work, as the list you walk down.
 *
 * This is the tickets read — `getBoard` for this project, the same record the
 * Board draws in lanes — so a project's own screen and the Board can never
 * disagree about what is on it. There is one of these in the product: the
 * rail's Tickets opens the project's own screen on this tab, and this tab is
 * local navigation inside that screen rather than a second way to get here.
 *
 * Where a row goes is the caller's, because the two mount points write the
 * address differently: reached through the rail it stays inside `?at=tickets`,
 * reached from the project's own screen it travels there. This component asks
 * the board and draws the answer; it never writes an address.
 *
 * The search is over the answer, not a second read: the contract declares no
 * ticket search, so filtering here narrows what already arrived and never
 * pretends to have asked ctower a question it has no operation for.
 */
export function Tasks({
  project,
  onOpen,
  onRaise,
  onBoard,
}: {
  readonly project: ProjectFacts;
  readonly onOpen: (ticketId: string) => void;
  readonly onRaise: () => void;
  readonly onBoard: () => void;
}): ReactElement {
  const [typed, setTyped] = useState("");
  const board = useBoard(project.key, 0);
  const cards = board.kind === "answered" ? board.value.cards : [];
  const kept = matching(cards, typed);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onRaise}>
          <Plus /> New task
        </Button>
        <Input
          value={typed}
          placeholder="Search these tickets"
          aria-label="Search these tickets"
          className="h-7 w-56 text-xs"
          onChange={(event): void => {
            setTyped(event.target.value);
          }}
        />
        <span className="flex-1" />
        <Button variant="quiet" size="sm" aria-label="List" aria-pressed className="text-fg">
          <LayoutList />
        </Button>
        <Button variant="quiet" size="sm" aria-label="Board" onClick={onBoard}>
          <Columns3 />
        </Button>
        {/* The rest of the reference's view controls. A tree needs a recorded
            parent, and grouping, sorting and filtering need a read that takes
            them; the board answers one project's cards in the record's order
            and nothing else, so these say what they are. */}
        <Inert className="px-1.5" reason="No read records a ticket's parent, so there is no tree.">
          <ListTree aria-hidden className="size-4" />
        </Inert>
        <Inert className="px-1.5" reason="Choosing columns is not built yet.">
          <Group aria-hidden className="size-4" />
        </Inert>
        <Inert className="px-1.5" reason="Filtering this list is not built yet.">
          <Filter aria-hidden className="size-4" />
        </Inert>
        <Inert
          className="px-1.5"
          reason="The board answers in the record's own order; re-sorting it here would overrule the record."
        >
          <SortAsc aria-hidden className="size-4" />
        </Inert>
      </div>

      {board.kind === "asking" ? <Asking what="Reading this project's work" /> : null}
      {board.kind === "refused" ? (
        <Refused problem={board.problem} action="No tickets were read. Reload to ask again." />
      ) : null}
      {board.kind === "unreachable" ? (
        <Unreachable detail={board.detail} action="Reload to ask again." />
      ) : null}
      {board.kind === "malformed" ? <Malformed detail={board.detail} /> : null}
      {board.kind === "answered" ? (
        <Listed cards={kept} searching={typed.trim() !== ""} total={cards.length} onOpen={onOpen} />
      ) : null}
    </>
  );
}

function Listed({
  cards,
  searching,
  total,
  onOpen,
}: {
  readonly cards: readonly BoardCard[];
  readonly searching: boolean;
  readonly total: number;
  readonly onOpen: (ticketId: string) => void;
}): ReactElement {
  if (total === 0) {
    return (
      <p className="m-0 py-6 text-sm text-muted">No ticket has been raised on this project.</p>
    );
  }
  // An empty project and a search that keeps nothing are different facts, and
  // are never drawn as one.
  if (cards.length === 0 && searching) {
    return <p className="m-0 py-6 text-sm text-muted">No ticket here matches that.</p>;
  }
  return <TicketTable cards={cards} onOpen={onOpen} />;
}

/**
 * The cards whose ticket number or title carry what was typed. The order is
 * untouched: the projection serves its cards in the record's own order, and a
 * search that re-ranked them would answer a question the operator did not ask.
 */
function matching(cards: readonly BoardCard[], typed: string): readonly BoardCard[] {
  const wanted = typed.trim().toLowerCase();
  if (wanted === "") {
    return cards;
  }
  return cards.filter(
    (card) =>
      card.title.toLowerCase().includes(wanted) ||
      (card.display_key ?? "").toLowerCase().includes(wanted)
  );
}
