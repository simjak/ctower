import { Plus } from "lucide-react";
import type { ReactElement } from "react";
import { cn } from "../../ui/cn";
import { Button, Chip, Input } from "../../ui/primitives";
import { CardTile } from "./CardTile";
import { heldIn, laneName, standing, HERE, RECORDED_LANES, REFERENCE_LANES } from "./fixtures";
import type { MockLane } from "./fixtures";

/**
 * The board: the project's tickets, read as columns.
 *
 * Two shapes, and the difference between them is the whole ruling this bench
 * asks for. **Recorded** is the six lanes ctower keeps, and a card carries only
 * what a read answers with. **Reference** is the operator's own kanban as he
 * drew it — seven columns and a face on every card — so he can see what the
 * record would have to learn before that board could be true.
 *
 * Which project it shows is not this screen's question: the switcher in the
 * rail governs the project workspace, and the board is handed one.
 */
export type BoardShape = "recorded" | "reference";

export function BoardScreen({ shape }: { readonly shape: BoardShape }): ReactElement {
  const lanes = shape === "reference" ? REFERENCE_LANES : RECORDED_LANES;
  return (
    <>
      <Head lanes={lanes} />
      <Bar />
      <div className={cn("grid gap-3", shape === "reference" ? "grid-cols-7" : "grid-cols-6")}>
        {lanes.map((lane) => (
          <Lane key={lane} lane={lane} face={shape === "reference"} />
        ))}
      </div>
    </>
  );
}

/** Whose board this is, and the one line that says whether it needs a person. */
function Head({ lanes }: { readonly lanes: readonly MockLane[] }): ReactElement {
  return (
    <header className="mb-4 flex flex-wrap items-center gap-3">
      <h1 className="m-0 min-w-0 truncate text-xl leading-tight font-bold tracking-[-0.02em]">
        {HERE.name}
      </h1>
      <Chip>{HERE.prefix}</Chip>
      <span className="text-sm text-muted">{standing(lanes)}</span>
    </header>
  );
}

/**
 * The one primary act, the way to narrow what is here, and the toggle.
 *
 * The toggle is the Tickets list's own: the list and the board are one read in
 * two shapes, so moving between them is a switch rather than a journey through
 * the rail.
 */
function Bar(): ReactElement {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-2.5">
      <Button variant="primary" size="sm">
        <Plus /> New ticket
      </Button>
      <Input
        defaultValue=""
        placeholder="Search these tickets"
        aria-label="Search these tickets"
        className="h-7 w-60 text-xs"
      />
      <span className="flex-1" />
      <Shapes />
    </div>
  );
}

function Shapes(): ReactElement {
  return (
    <div
      role="group"
      aria-label="How these tickets are shown"
      className="inline-flex gap-0.5 rounded-md bg-raised p-0.5"
    >
      <Button variant="quiet" size="sm" className="h-6 font-medium">
        List
      </Button>
      <Button variant="quiet" size="sm" aria-pressed className="h-6 bg-card text-fg">
        Board
      </Button>
    </div>
  );
}

/**
 * One lane, drawn as a column.
 *
 * An empty lane keeps its column: a board whose columns come and go as work
 * moves is one the eye has to re-learn every morning, and an empty lane is a
 * fact worth seeing. The head carries no mark — a lane is a place work sits,
 * not one of the six states the CLI prints a glyph for.
 */
function Lane({ lane, face }: { readonly lane: MockLane; readonly face: boolean }): ReactElement {
  const held = heldIn(lane);
  return (
    <section aria-label={laneName(lane)} className="min-w-0">
      {/* The count sits against its own label rather than at the column's right
          edge: with no rule between columns, a right-aligned number reads as
          though it belongs to the heading beside it. */}
      <header className="mb-3 flex items-baseline gap-1.5">
        <h2 className="m-0 min-w-0 truncate text-[11.5px] tracking-[0.08em] text-muted uppercase">
          {laneName(lane)}
        </h2>
        <span className="text-2xs text-muted">{held.length}</span>
      </header>
      <div className="flex flex-col gap-2.5">
        {held.map((card) => (
          <CardTile key={card.key ?? card.title} card={card} face={face} />
        ))}
      </div>
    </section>
  );
}
