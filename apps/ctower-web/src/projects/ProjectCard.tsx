import { Folder } from "lucide-react";
import type { ReactElement } from "react";
import type { BoardView } from "@ctower/client";
import type { Answer } from "../api/client";
import { Mark } from "../ui/marks";
import { cn } from "../ui/cn";
import { Chip } from "../ui/primitives";
import { laneCount } from "./board";
import type { ProjectFacts } from "./read";

/**
 * One project, as a card.
 *
 * Two facts arrive at different times and the card says so. What the company
 * records — the name, the ticket prefix, the repository, the goals it serves —
 * came with the bundle and is on the card the moment it draws. What is
 * happening on it is that project's own board read, and a card whose board has
 * not answered says which of the four things happened to it instead of drawing
 * a blank where a count goes. A missing number and a zero are different facts.
 *
 * The whole card is the way in. Entering it scopes every project screen to this
 * project, which is what the card is for.
 */
export function ProjectCard({
  project,
  board,
  onOpen,
}: {
  readonly project: ProjectFacts;
  readonly board: Answer<BoardView>;
  readonly onOpen: (key: string) => void;
}): ReactElement {
  return (
    <button
      type="button"
      onClick={(): void => {
        onOpen(project.key);
      }}
      className={cn(
        "flex cursor-pointer flex-col rounded-md border border-line bg-card p-4 text-left",
        "hover:border-amber/60 hover:bg-raised"
      )}
    >
      <div className="flex w-full items-center gap-2">
        <Folder aria-hidden className="size-4 shrink-0 text-muted" />
        <span className="min-w-0 flex-1 truncate font-semibold text-fg">{project.name}</span>
        {project.prefix === null ? null : <Chip>{project.prefix}</Chip>}
      </div>

      <p className="m-0 mt-2 truncate text-xs text-muted">
        {project.repository ?? "No repository recorded"}
      </p>

      <div className="mt-3 flex w-full flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <Standing board={board} />
      </div>

      <div className="mt-3 flex w-full flex-wrap items-center gap-1.5 border-t border-line pt-3">
        {project.goals.length === 0 ? (
          <span className="text-2xs text-muted">Serves no recorded goal</span>
        ) : (
          project.goals.map((goal) => (
            <Chip key={goal} tone="amber">
              {goal}
            </Chip>
          ))
        )}
      </div>
    </button>
  );
}

/** The three board numbers, or the one thing that happened instead. */
function Standing({ board }: { readonly board: Answer<BoardView> }): ReactElement {
  switch (board.kind) {
    case "asking":
      return <Instead mark="working" text="Reading the board" tone="text-muted" />;
    case "refused":
      return <Instead mark="dead" text="The board refused this read" tone="text-danger" />;
    case "unreachable":
      return <Instead mark={null} text="ctower did not answer" tone="text-muted" />;
    case "malformed":
      return <Instead mark="warn" text="Unreadable answer" tone="text-muted" />;
    case "answered":
      return (
        <>
          <Counted label="tickets" count={board.value.cards.length} />
          <Counted label="in progress" count={laneCount(board.value, "in_progress")} />
          <Counted label="complete" count={laneCount(board.value, "complete")} />
        </>
      );
  }
}

function Counted({
  label,
  count,
}: {
  readonly label: string;
  readonly count: number;
}): ReactElement {
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="font-semibold text-fg">{count}</span>
      <span className="text-muted">{label}</span>
    </span>
  );
}

function Instead({
  mark,
  text,
  tone,
}: {
  readonly mark: "working" | "dead" | "warn" | null;
  readonly text: string;
  readonly tone: string;
}): ReactElement {
  return (
    <span className={cn("inline-flex items-center gap-1.5", tone)}>
      {mark === null ? null : <Mark name={mark} />}
      {text}
    </span>
  );
}
