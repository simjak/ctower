import { RotateCw } from "lucide-react";
import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import type { BoardCard, BoardView, CompanyBundleDocument, MovementEvent } from "@ctower/client";
import type { Answer } from "../api/client";
import { Button, Chip, PageHead } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { Advance } from "./Advance";
import { Column } from "./Column";
import { Conveyor } from "./Conveyor";
import { columnsOf, freshnessOf, projectsOf } from "./lanes";
import type { Project } from "./lanes";
import type { Moved } from "./conveyor";
import { useMovement } from "./useMovement";
import { atPriority, countsOf, PriorityField } from "./PriorityField";
import type { PriorityChoice } from "./PriorityField";
import { ProjectField } from "./ProjectField";
import { TicketPanel } from "./TicketPanel";
import { useBoard } from "./useBoard";

/**
 * The Board, on either of the two axes the record actually keeps.
 *
 * **Lanes** are the projection's summary of where a card stands — six of them,
 * closed, and `getBoard` puts every card in exactly one. **Stages** are the
 * workflow's own positions: the company definition declares them, the ticket
 * carries the one it stands at, and the record moves it between them. Neither
 * is derived from the other and the switch says which one is being read.
 *
 * The page is still. It reads once when the project changes and once more when
 * the operator asks it to, because `DESIGN.md` reserves motion for real work
 * moving and a board that repaints on a timer moves when nothing has. The one
 * thing that animates is a card the record moved between two of those reads,
 * which is the conveyor the design system reserves its motion budget for.
 *
 * The project and the axis both live in the address, so a board is a link — the
 * same board opens for whoever the operator sends it to.
 */
export function BoardPage({ company }: { readonly company: CompanyBundleDocument }): ReactElement {
  const projects = projectsOf(company);
  const [projectKey, setProjectKey] = useState<string | null>(() => opensOn(projects));
  const [reloadKey, setReloadKey] = useState(0);
  const [open, setOpen] = useState<BoardCard | null>(null);
  const [priority, setPriority] = useState<PriorityChoice>("any");
  const [axis, setAxis] = useState<Axis>(() => opensAlong());
  const board = useBoard(projectKey, reloadKey);
  const movement = useMovement(projectKey, reloadKey);
  const answered = board.kind === "answered" ? board.value.cards : null;
  const moves = movement.answer.kind === "answered" ? movement.answer.value : [];

  const choose = useCallback((key: string): void => {
    setOpen(null);
    setProjectKey(key);
    rememberProject(key);
  }, []);

  return (
    <>
      <PageHead title="Board" subtitle={<Standing board={board} projectKey={projectKey} />}>
        <AxisField axis={axis} onChoose={goAlong(setAxis)} />
        <ProjectField projectKey={projectKey} projects={projects} onChoose={choose} />
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
        <Unopened projects={projects} onChoose={choose} />
      ) : (
        <Lanes
          board={board}
          axis={axis}
          company={company}
          movement={moves}
          moved={movement.moved}
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
          advance={
            axis === "stages" ? (
              <Advance
                company={company}
                projectKey={projectKey}
                ticketId={open.ticket_id}
                stageKey={open.stage_key}
                movement={moves}
                onMoved={(): void => {
                  setReloadKey((count) => count + 1);
                }}
              />
            ) : undefined
          }
          onClose={(): void => {
            setOpen(null);
          }}
        />
      )}
    </>
  );
}

/**
 * No project yet, and the one action that fixes it sits next to the sentence
 * that says so. The choices are the definition's own projects; a company whose
 * definition names none gets the sentence and the field, because there is
 * nothing real to offer and a made-up suggestion would be worse than none.
 */
function Unopened({
  projects,
  onChoose,
}: {
  readonly projects: readonly Project[];
  readonly onChoose: (key: string) => void;
}): ReactElement {
  return (
    <div className="py-6">
      <p className="m-0 text-sm text-muted">
        Name the project this board reads, and it opens on that project&rsquo;s work.
      </p>
      {projects.length === 0 ? null : (
        <div className="mt-3 flex flex-wrap gap-2">
          {projects.map((project) => (
            <Button
              key={project.key}
              variant="ghost"
              size="sm"
              onClick={(): void => {
                onChoose(project.key);
              }}
            >
              {project.name}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

function Lanes({
  board,
  axis,
  company,
  movement,
  moved,
  priority,
  selectedId,
  onOpen,
  onAnyPriority,
}: {
  readonly board: Answer<BoardView>;
  readonly axis: Axis;
  readonly company: CompanyBundleDocument;
  readonly movement: readonly MovementEvent[];
  readonly moved: readonly Moved[];
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
          axis={axis}
          company={company}
          movement={movement}
          moved={moved}
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
  axis,
  company,
  movement,
  moved,
  priority,
  selectedId,
  onOpen,
  onAnyPriority,
}: {
  readonly view: BoardView;
  readonly axis: Axis;
  readonly company: CompanyBundleDocument;
  readonly movement: readonly MovementEvent[];
  readonly moved: readonly Moved[];
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
  if (axis === "stages") {
    return (
      <Conveyor
        company={company}
        cards={kept}
        movement={movement}
        moved={moved}
        selectedId={selectedId}
        onOpen={onOpen}
      />
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
 * Which axis the board is read along.
 *
 * Two words, both of them the record's: a **lane** is what `getBoard` puts a
 * card in, a **stage** is where the workflow has it standing. The control names
 * them and does not translate either into the other.
 */
export type Axis = "lanes" | "stages";

const AXES: readonly Axis[] = ["lanes", "stages"];

const AXIS_LABEL: Readonly<Record<Axis, string>> = {
  lanes: "Lanes",
  stages: "Stages",
};

function AxisField({
  axis,
  onChoose,
}: {
  readonly axis: Axis;
  readonly onChoose: (axis: Axis) => void;
}): ReactElement {
  return (
    <div role="group" aria-label="Read the board along" className="flex items-center gap-1">
      {AXES.map((choice) => (
        <Button
          key={choice}
          variant={choice === axis ? "ghost" : "quiet"}
          size="sm"
          aria-pressed={choice === axis}
          className={choice === axis ? "border-amber text-fg" : undefined}
          onClick={(): void => {
            onChoose(choice);
          }}
        >
          {AXIS_LABEL[choice]}
        </Button>
      ))}
    </div>
  );
}

/** The axis is in the address too, so a stage view is as linkable as a board. */
function opensAlong(): Axis {
  return new URLSearchParams(window.location.search).get("along") === "stages" ? "stages" : "lanes";
}

function goAlong(setAxis: (axis: Axis) => void): (axis: Axis) => void {
  return (axis: Axis): void => {
    setAxis(axis);
    const url = new URL(window.location.href);
    url.searchParams.set("along", axis);
    window.history.replaceState(null, "", url);
  };
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

/**
 * Which project the board opens on.
 *
 * The address wins, so a board is a link. Failing that, a company whose
 * definition names exactly one project has no question to ask and the board
 * opens on it; a company that names several is asked, because picking the
 * alphabetically first one would be a guess dressed as a default.
 */
function opensOn(projects: readonly Project[]): string | null {
  const asked = new URLSearchParams(window.location.search).get("project");
  if (asked !== null && asked !== "") {
    return asked;
  }
  return projects.length === 1 ? (projects[0]?.key ?? null) : null;
}

function rememberProject(key: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set("project", key);
  window.history.replaceState(null, "", url);
}
