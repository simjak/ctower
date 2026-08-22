import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import type { BoardCard, BoardView, CompanyBundleDocument } from "@ctower/client";
import type { Answer } from "../api/client";
import { Button, Chip, PageHead } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { CardTile } from "./CardTile";
import { Filters } from "./Filters";
import { atPriority, columnsOf, freshnessOf, PRIORITIES, projectsOf } from "./lanes";
import type { PriorityChoice } from "./lanes";
import { TicketPanel } from "./TicketPanel";
import { useBoard } from "./useBoard";

/**
 * The Board: six lanes of real work, and what is behind one card.
 *
 * The page holds exactly one selection. Opening a card does not navigate and
 * does not animate: the panel takes the space to the right of the lanes and the
 * six columns narrow to share what is left, instantly, because `DESIGN.md`
 * spends motion only when real work moves and a layout is not work.
 */
export function BoardPage({
  definition,
}: {
  readonly definition: CompanyBundleDocument;
}): ReactElement {
  const projects = useMemo(() => projectsOf(definition), [definition]);
  const [projectKey, setProjectKey] = useState<string | null>(projects[0]?.key ?? null);
  const [priority, setPriority] = useState<PriorityChoice>("any");
  const [openTicket, setOpenTicket] = useState<string | null>(null);
  const board = useBoard(projectKey);

  if (projectKey === null) {
    return (
      <>
        <PageHead title="Board" />
        <p className="m-0 py-6 text-sm text-muted">
          This company names no project yet. Add one on the Company page.
        </p>
      </>
    );
  }

  const cards = board.kind === "answered" ? board.value.cards : [];
  const kept = atPriority(cards, priority);
  const open = kept.find((card) => card.ticket_id === openTicket) ?? null;

  return (
    <>
      <PageHead title="Board" subtitle={<Standing board={board} kept={kept.length} />} />
      <Filters
        projects={projects}
        projectKey={projectKey}
        onProject={(key): void => {
          setProjectKey(key);
          setOpenTicket(null);
        }}
        priority={priority}
        onPriority={setPriority}
        counts={board.kind === "answered" ? countsOf(board.value.cards) : null}
      />
      {board.kind === "answered" ? (
        <div
          className={
            open === null
              ? "grid gap-3"
              : "grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start"
          }
        >
          <Lanes
            cards={kept}
            empty={cards.length}
            openTicket={openTicket}
            onOpen={setOpenTicket}
            onAnyPriority={(): void => {
              setPriority("any");
            }}
          />
          {open === null ? null : (
            <TicketPanel
              projectKey={projectKey}
              card={open}
              onClose={(): void => {
                setOpenTicket(null);
              }}
            />
          )}
        </div>
      ) : (
        <Unanswered board={board} />
      )}
    </>
  );
}

/** The six columns, or the one sentence that says why there are no cards in them. */
function Lanes({
  cards,
  empty,
  openTicket,
  onOpen,
  onAnyPriority,
}: {
  readonly cards: readonly BoardCard[];
  /** How many cards the read answered before the filter narrowed them. */
  readonly empty: number;
  readonly openTicket: string | null;
  readonly onOpen: (ticketId: string) => void;
  readonly onAnyPriority: () => void;
}): ReactElement {
  if (empty === 0) {
    return <p className="m-0 py-6 text-sm text-muted">This project has no tickets yet.</p>;
  }
  if (cards.length === 0) {
    return (
      <div className="py-6">
        <p className="m-0 text-sm text-muted">No ticket on this board carries that priority.</p>
        <Button size="sm" className="mt-2" onClick={onAnyPriority}>
          Show any priority
        </Button>
      </div>
    );
  }
  return (
    // Six equal shares of whatever width there is, and never a scrollbar. The
    // shell caps content at 1200px and a detail panel takes a third of it, so
    // the alternative was a track that scrolls and slices a card in half at the
    // panel's edge — which reads as a broken column, not as more board. A lane
    // the operator cannot see is a lane he stops counting.
    <div className="grid grid-cols-6 gap-2.5">
      {columnsOf(cards).map((column) => (
        <section key={column.lane} className="min-w-0">
          <header className="mb-2 flex items-baseline gap-2 border-b border-line pb-1.5">
            <h2 className="m-0 text-xs font-semibold tracking-[-0.01em]">{column.label}</h2>
            <span className="text-2xs text-muted">{column.cards.length}</span>
          </header>
          <ul className="m-0 grid list-none gap-2 p-0">
            {column.cards.map((card) => (
              <CardTile
                key={card.ticket_id}
                card={card}
                selected={card.ticket_id === openTicket}
                onOpen={(): void => {
                  onOpen(card.ticket_id);
                }}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/**
 * What the head says about the read, and only what is known.
 *
 * A projection that has not caught up says so. `STATE_UNKNOWN` is not "current",
 * and a stale count presented as the truth is the one thing a board must never
 * do.
 */
function Standing({
  board,
  kept,
}: {
  readonly board: Answer<BoardView>;
  readonly kept: number;
}): ReactElement | null {
  if (board.kind !== "answered") {
    return null;
  }
  const freshness = freshnessOf(board.value);
  return (
    <>
      <span>
        {String(kept)} of {String(board.value.cards.length)} cards
      </span>
      {freshness.kind === "current" ? null : (
        <Chip tone="amber">{freshness.kind === "behind" ? freshness.detail : "State unknown"}</Chip>
      )}
    </>
  );
}

function Unanswered({ board }: { readonly board: Answer<BoardView> }): ReactElement | null {
  switch (board.kind) {
    case "asking":
      return <Asking what="Reading this board" />;
    case "refused":
      return (
        <Refused
          problem={board.problem}
          action="Nothing was read. Choose a project to ask again."
        />
      );
    case "unreachable":
      return (
        <Unreachable
          detail={board.detail}
          action="This is not an empty board; it is a board that was not read."
        />
      );
    case "malformed":
      return <Malformed detail={board.detail} />;
    case "answered":
      return null;
  }
}

function countsOf(cards: readonly BoardCard[]): Readonly<Record<PriorityChoice, number>> {
  const counts: Record<PriorityChoice, number> = { any: cards.length, P0: 0, P1: 0, P2: 0 };
  for (const choice of PRIORITIES) {
    counts[choice] = atPriority(cards, choice).length;
  }
  return counts;
}
