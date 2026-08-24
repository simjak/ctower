import { RotateCw } from "lucide-react";
import { useState } from "react";
import type { ReactElement } from "react";
import type { BoardCard, BoardView } from "@ctower/client";
import type { Answer } from "../api/client";
import { Button, Chip, PageHead } from "../ui/primitives";
import type { DestinationKey } from "../shell/destinations";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { Column } from "./Column";
import { columnsOf, freshnessOf } from "./lanes";
import { atPriority, countsOf, PriorityField } from "./PriorityField";
import type { PriorityChoice } from "./PriorityField";
import { TicketPanel } from "./TicketPanel";
import { useBoard } from "./useBoard";

/**
 * The Board. Six lanes, the cards the projection holds, and nothing else.
 *
 * The page is still. It reads once when the project changes and once more when
 * the operator asks it to, because `DESIGN.md` reserves motion for real work
 * moving and a board that repaints on a timer moves when nothing has.
 *
 * Which project it reads is not this screen's question. The rail governs the
 * project workspace and the address carries the answer, so the board is handed
 * one and shows it — one chooser for every project-scoped screen, and a board
 * that is a link because the address it was opened from says which project it
 * is about.
 */
export function BoardPage({
  projectKey,
  onGoProjects,
}: {
  /** The project the rail is pointed at; null only when the company has none. */
  readonly projectKey: string | null;
  readonly onGoProjects: (key: DestinationKey) => void;
}): ReactElement {
  const [reloadKey, setReloadKey] = useState(0);
  const [open, setOpen] = useState<BoardCard | null>(null);
  const [priority, setPriority] = useState<PriorityChoice>("any");
  const board = useBoard(projectKey, reloadKey);
  const answered = board.kind === "answered" ? board.value.cards : null;

  return (
    <>
      <PageHead title="Board" subtitle={<Standing board={board} projectKey={projectKey} />}>
        <PriorityField priority={priority} counts={countsOf(answered)} onChoose={setPriority} />
        <Button
          variant="ghost"
          size="sm"
          disabled={projectKey === null}
          onClick={(): void => {
            setReloadKey((count) => count + 1);
          }}
        >
          <RotateCw /> Read again
        </Button>
      </PageHead>

      {projectKey === null ? (
        <Unopened onGoProjects={onGoProjects} />
      ) : (
        <Lanes
          board={board}
          priority={priority}
          selectedId={open?.ticket_id ?? null}
          onOpen={setOpen}
          onAnyPriority={(): void => {
            setPriority("any");
          }}
        />
      )}

      {open === null || projectKey === null ? null : (
        <TicketPanel
          card={open}
          projectKey={projectKey}
          onClose={(): void => {
            setOpen(null);
          }}
        />
      )}
    </>
  );
}

/**
 * No project in the rail, so no board to read. This company records none yet,
 * and the one action that fixes it sits next to the sentence that says so.
 */
function Unopened({
  onGoProjects,
}: {
  readonly onGoProjects: (key: DestinationKey) => void;
}): ReactElement {
  return (
    <div className="py-6">
      <p className="m-0 text-sm text-muted">
        This company has no project yet, so there is no board to read.
      </p>
      <Button
        variant="primary"
        className="mt-3"
        onClick={(): void => {
          onGoProjects("projects");
        }}
      >
        Open Projects
      </Button>
    </div>
  );
}

function Lanes({
  board,
  priority,
  selectedId,
  onOpen,
  onAnyPriority,
}: {
  readonly board: Answer<BoardView>;
  readonly priority: PriorityChoice;
  readonly selectedId: string | null;
  readonly onOpen: (card: BoardCard) => void;
  readonly onAnyPriority: () => void;
}): ReactElement {
  switch (board.kind) {
    case "asking":
      return <Asking what="Reading this board" />;
    case "refused":
      return (
        <Refused
          problem={board.problem}
          action="No cards were read. Check the project key and ask again."
        />
      );
    case "unreachable":
      return (
        <Unreachable
          detail={board.detail}
          action="This is not an empty board; it is a board that was not read. Ask again."
        />
      );
    case "malformed":
      return <Malformed detail={board.detail} />;
    case "answered":
      return (
        <Grid
          view={board.value}
          priority={priority}
          selectedId={selectedId}
          onOpen={onOpen}
          onAnyPriority={onAnyPriority}
        />
      );
  }
}

function Grid({
  view,
  priority,
  selectedId,
  onOpen,
  onAnyPriority,
}: {
  readonly view: BoardView;
  readonly priority: PriorityChoice;
  readonly selectedId: string | null;
  readonly onOpen: (card: BoardCard) => void;
  readonly onAnyPriority: () => void;
}): ReactElement {
  if (view.cards.length === 0) {
    return <p className="m-0 py-6 text-sm text-muted">This project holds no tickets yet.</p>;
  }
  // An empty board and a filter that keeps nothing are different facts and are
  // never drawn as one: the second one names the filter and offers to undo it,
  // because the cards are there and the operator hid them.
  const kept = atPriority(view.cards, priority);
  if (kept.length === 0) {
    return (
      <div className="py-6">
        <p className="m-0 text-sm text-muted">No ticket on this board carries that priority.</p>
        <Button variant="ghost" size="sm" className="mt-2" onClick={onAnyPriority}>
          Show any priority
        </Button>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-6 gap-2">
      {columnsOf(kept).map((column) => (
        <Column key={column.lane} column={column} selectedId={selectedId} onOpen={onOpen} />
      ))}
    </div>
  );
}

/**
 * What the head says about the read, and only what is known.
 *
 * `STATE_UNKNOWN` is not `current` and never renders as one, and a projection
 * that has not folded everything the record holds says it is catching up rather
 * than presenting its count as complete. The two watermarks are record
 * positions, so they stay in the hover instead of being drawn as a number of
 * tickets they are not.
 */
function Standing({
  board,
  projectKey,
}: {
  readonly board: Answer<BoardView>;
  readonly projectKey: string | null;
}): ReactElement {
  if (projectKey === null) {
    return <Chip>no project</Chip>;
  }
  switch (board.kind) {
    case "asking":
      return <Chip>reading</Chip>;
    case "refused":
      return <Chip tone="danger">{board.problem.code}</Chip>;
    case "unreachable":
      return <Chip>not read</Chip>;
    case "malformed":
      return <Chip tone="amber">contract</Chip>;
    case "answered":
      return <Counted view={board.value} />;
  }
}

function Counted({ view }: { readonly view: BoardView }): ReactElement {
  const freshness = freshnessOf(view);
  return (
    <>
      <Chip>
        {view.cards.length} {view.cards.length === 1 ? "card" : "cards"}
      </Chip>
      {freshness.kind === "current" ? <Chip tone="ok">current</Chip> : null}
      {freshness.kind === "behind" ? (
        <Chip tone="amber" title={freshness.detail}>
          catching up
        </Chip>
      ) : null}
      {freshness.kind === "unknown" ? <Chip>not known</Chip> : null}
    </>
  );
}
