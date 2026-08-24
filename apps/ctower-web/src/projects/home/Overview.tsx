import type { ReactElement } from "react";
import type { BoardView } from "@ctower/client";
import type { Answer } from "../../api/client";
import { Mark } from "../../ui/marks";
import { Card, CardBody, CardHeader, CardTitle, Chip } from "../../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../../wizard/states";
import { useBoard } from "../../tickets/reads";
import {
  healthWord,
  LANE_MARK,
  LANE_WORD,
  LANES,
  laneCount,
  priorityCount,
  PRIORITIES,
} from "../board";
import { kindCounts } from "../read";
import type { ProjectFacts } from "../read";

/**
 * One project, in the two things this tower knows about it: what the company
 * records under it, which the bundle already answered, and what is on its
 * board, which is its own read and its own outcome.
 *
 * The two sit side by side and neither speaks for the other. A board that
 * refused leaves the record's own column standing.
 */
export function Overview({ project }: { readonly project: ProjectFacts }): ReactElement {
  const board = useBoard(project.key, 0);

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>What is in it</CardTitle>
          <span className="flex-1" />
          <Chip>
            {project.scoped.length} {project.scoped.length === 1 ? "component" : "components"}
          </Chip>
        </CardHeader>
        <CardBody className="space-y-3">
          {project.scoped.length === 0 ? (
            <p className="m-0 text-sm text-muted">
              Nothing this company records belongs to this project yet.
            </p>
          ) : (
            kindCounts(project.scoped).map((counted) => (
              <Kind
                key={counted.kind}
                label={counted.label}
                count={counted.count}
                names={counted.names}
              />
            ))
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>On the board</CardTitle>
          <span className="flex-1" />
          {board.kind === "answered" ? (
            <Chip tone={board.value.health === "CURRENT" ? "ok" : "neutral"}>
              {healthWord(board.value)}
            </Chip>
          ) : null}
        </CardHeader>
        <CardBody>
          <Board board={board} project={project.name} />
        </CardBody>
      </Card>
    </div>
  );
}

/**
 * One kind of thing, how many of them, and what they are called. A component
 * whose payload named nothing contributes to the count and to nothing else —
 * its key is machine text and would say nothing to the person reading this.
 */
function Kind({
  label,
  count,
  names,
}: {
  readonly label: string;
  readonly count: number;
  readonly names: readonly string[];
}): ReactElement {
  return (
    <div>
      <div className="flex items-baseline gap-2 border-b border-line pb-1 text-xs">
        <span className="text-fg">{label}</span>
        <span className="flex-1" />
        <span className="text-muted">{count}</span>
      </div>
      {names.length === 0 ? null : (
        <p className="mt-1.5 mb-0 text-xs text-muted">{names.join(" · ")}</p>
      )}
    </div>
  );
}

function Board({
  board,
  project,
}: {
  readonly board: Answer<BoardView>;
  readonly project: string;
}): ReactElement {
  switch (board.kind) {
    case "asking":
      return <Asking what={`Reading the board for ${project}`} />;
    case "refused":
      return <Refused problem={board.problem} action="This project's board was not read." />;
    case "unreachable":
      return <Unreachable detail={board.detail} action="Reload to ask again." />;
    case "malformed":
      return <Malformed detail={board.detail} />;
    case "answered":
      return <Counted view={board.value} />;
  }
}

function Counted({ view }: { readonly view: BoardView }): ReactElement {
  return (
    <>
      <div className="space-y-1">
        {LANES.map((lane) => (
          <div key={lane} className="flex items-center gap-2 text-sm">
            <Mark name={LANE_MARK[lane]} />
            <span className="text-fg">{LANE_WORD[lane]}</span>
            <span className="flex-1 border-b border-dotted border-line" />
            <span className="text-muted">{laneCount(view, lane)}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        {PRIORITIES.map((priority) => (
          <Chip
            key={priority}
            tone={priority === "P0" && priorityCount(view, priority) > 0 ? "amber" : "neutral"}
          >
            {priority} {priorityCount(view, priority)}
          </Chip>
        ))}
      </div>
    </>
  );
}
