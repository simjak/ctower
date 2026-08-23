import type { ReactElement } from "react";
import type { BoardCard, CompanyBundleDocument, MovementEvent } from "@ctower/client";
import { Hint } from "../ui/form";
import { Chip, Mono } from "../ui/primitives";
import { cn } from "../ui/cn";
import { CardTile } from "./CardTile";
import { conveyorOf } from "./conveyor";
import type { Moved, StageColumn } from "./conveyor";

/**
 * Tickets moving through the stages their workflow declares.
 *
 * The lane view answers "where does the projection put this card". This answers
 * the question the workflow itself asks: which stage is it standing at, what
 * does the record require before it may leave, and what has actually moved.
 *
 * Every column is a stage the company definition declares, in the order it
 * declares them. Every card sits at the stage its own `stage_key` names. Every
 * gate between two columns is that transition's own `predicate_ref`. A card the
 * record places nowhere is not placed here either.
 */
export function Conveyor({
  company,
  cards,
  movement,
  moved,
  selectedId,
  onOpen,
}: {
  readonly company: CompanyBundleDocument;
  readonly cards: readonly BoardCard[];
  readonly movement: readonly MovementEvent[];
  /** The moves recorded since the last read; the only thing that animates. */
  readonly moved: readonly Moved[];
  readonly selectedId: string | null;
  readonly onOpen: (card: BoardCard) => void;
}): ReactElement {
  const conveyor = conveyorOf(company, cards, movement);

  if (conveyor.workflow === null) {
    return (
      <div className="py-6">
        <p className="m-0 text-sm text-muted">{conveyor.silence}</p>
        {conveyor.unplaced.length === 0 ? null : (
          <Unplaced cards={conveyor.unplaced} selectedId={selectedId} onOpen={onOpen} />
        )}
      </div>
    );
  }

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-muted">
        <Mono>
          {conveyor.workflow.key}@{conveyor.workflow.revision}
        </Mono>
        {conveyor.workflow.status === null ? null : <Chip>{conveyor.workflow.status}</Chip>}
        <Hint text="Stages, their order and the gate on each move are the workflow's own; the cards are the board's. Nothing here is derived." />
      </div>

      <div className="flex items-stretch gap-1 overflow-x-auto pb-1">
        {conveyor.stages.map((stage, index) => (
          <div key={stage.key} className="flex min-w-0 items-stretch gap-1">
            {index === 0 ? null : <Gate stage={conveyor.stages[index - 1]} />}
            <Stage stage={stage} moved={moved} selectedId={selectedId} onOpen={onOpen} />
          </div>
        ))}
      </div>

      {conveyor.strays.length === 0 ? null : (
        <Aside
          title="Standing at a stage this workflow does not declare"
          cards={conveyor.strays}
          selectedId={selectedId}
          onOpen={onOpen}
        />
      )}
      {conveyor.unplaced.length === 0 ? null : (
        <Unplaced cards={conveyor.unplaced} selectedId={selectedId} onOpen={onOpen} />
      )}
    </>
  );
}

/**
 * One stage, and the cards standing at it.
 *
 * An empty stage keeps its column, because an empty stage is a fact worth
 * seeing — on the tower this was built against, `verify` and `close` are empty
 * precisely because the record refuses the moves into them.
 */
function Stage({
  stage,
  moved,
  selectedId,
  onOpen,
}: {
  readonly stage: StageColumn;
  readonly moved: readonly Moved[];
  readonly selectedId: string | null;
  readonly onOpen: (card: BoardCard) => void;
}): ReactElement {
  return (
    <section aria-label={stage.key} className="flex w-[184px] min-w-0 shrink-0 flex-col">
      <header className="flex items-baseline gap-1.5 border-b border-line pb-1.5">
        <h2 className="m-0 min-w-0 truncate text-2xs leading-none font-medium text-muted">
          {stage.label}
        </h2>
        <span className="text-2xs text-muted">{stage.cards.length}</span>
        {stage.activityClass === null ? null : (
          <span className="ml-auto text-2xs text-muted">{stage.activityClass}</span>
        )}
      </header>
      <div className="mt-2 flex max-h-[calc(100dvh-250px)] flex-col gap-2 overflow-y-auto pr-1">
        {stage.cards.map((card) => (
          <Arriving key={card.ticket_id} card={card} moved={moved}>
            <CardTile card={card} selected={card.ticket_id === selectedId} onOpen={onOpen} />
          </Arriving>
        ))}
      </div>
    </section>
  );
}

/**
 * A card that just arrived, and only if it did.
 *
 * The animation is keyed on the move's own record position through the element
 * key, so a card that moved twice animates twice and a card that has not moved
 * carries no animation class at all. The direction is the travel: a card that
 * came from an earlier stage slides in from the left.
 */
function Arriving({
  card,
  moved,
  children,
}: {
  readonly card: BoardCard;
  readonly moved: readonly Moved[];
  readonly children: ReactElement;
}): ReactElement {
  const move = moved.find((entry) => entry.ticketId === card.ticket_id);
  if (move === undefined) {
    return children;
  }
  return (
    <div className="conveyor-arrive" style={{ ["--conveyor-travel" as string]: "24px" }}>
      {children}
      <p className="mt-1 mb-0 text-2xs text-muted">
        moved {move.from === "" ? "in" : `from ${move.from}`}
      </p>
    </div>
  );
}

/**
 * The gate between two stages: what the record requires before that move is
 * allowed, in the definition's own words.
 *
 * This is not a prediction about any card. It is the transition's declared
 * `predicate_ref`, drawn where the move happens. Whether a particular ticket
 * satisfies it is something only ctower can answer, and it answers it when the
 * move is attempted — which is why a refused move shows the refusal on the card
 * rather than a badge this screen made up.
 */
function Gate({ stage }: { readonly stage: StageColumn | undefined }): ReactElement {
  const predicate = stage?.leaving?.predicate ?? null;
  return (
    <div
      className="flex w-[104px] shrink-0 flex-col items-center pt-7"
      aria-hidden={predicate === null}
    >
      <span className="text-2xs leading-none text-muted">→</span>
      {predicate === null ? null : (
        <>
          {/* The gate is the whole point of the column between two stages, so
              it is never abbreviated: an operator who cannot read which
              predicate stands in the way is being shown decoration. */}
          <Mono className="mt-1.5 w-full text-center leading-tight break-words text-muted">
            {predicate}
          </Mono>
          <span className="sr-only">is required to leave {stage?.key ?? "this stage"}</span>
        </>
      )}
    </div>
  );
}

function Unplaced({
  cards,
  selectedId,
  onOpen,
}: {
  readonly cards: readonly BoardCard[];
  readonly selectedId: string | null;
  readonly onOpen: (card: BoardCard) => void;
}): ReactElement {
  return (
    <Aside
      title="Not in a workflow yet"
      note="The record places these at no stage: nothing has started a workflow on them."
      cards={cards}
      selectedId={selectedId}
      onOpen={onOpen}
    />
  );
}

function Aside({
  title,
  note,
  cards,
  selectedId,
  onOpen,
}: {
  readonly title: string;
  readonly note?: string;
  readonly cards: readonly BoardCard[];
  readonly selectedId: string | null;
  readonly onOpen: (card: BoardCard) => void;
}): ReactElement {
  return (
    <section aria-label={title} className="mt-5 border-t border-line pt-3">
      <header className="flex items-baseline gap-1.5">
        <h2 className="m-0 text-2xs leading-none font-medium text-muted">{title}</h2>
        <span className="text-2xs text-muted">{cards.length}</span>
      </header>
      {note === undefined ? null : <p className="mt-1 mb-0 text-2xs text-muted">{note}</p>}
      <div className={cn("mt-2 grid gap-2", "grid-cols-2 md:grid-cols-4 xl:grid-cols-6")}>
        {cards.map((card) => (
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
