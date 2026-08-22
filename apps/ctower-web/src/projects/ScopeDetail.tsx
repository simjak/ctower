import type { ReactElement } from "react";
import type { BoardView, CompanyBundleResource } from "@ctower/client";
import type { Answer } from "../api/client";
import { Mark } from "../ui/marks";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import {
  healthWord,
  LANE_MARK,
  LANE_WORD,
  LANES,
  laneCount,
  priorityCount,
  PRIORITIES,
} from "./board";
import { kindCounts } from "./read";
import type { ProjectScope } from "./read";

/**
 * One project, in the two things this tower knows about it: what is scoped to
 * it, which the bundle already answered, and what is on its board, which is its
 * own read and its own outcome.
 *
 * The two sit side by side and neither speaks for the other. A board that
 * refused leaves the scope column standing.
 */
export function ScopeDetail({
  scope,
  board,
}: {
  readonly scope: ProjectScope;
  readonly board: Answer<BoardView>;
}): ReactElement {
  return (
    <div className="mt-4 grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Scoped to {scope.key}</CardTitle>
          <span className="flex-1" />
          <Chip>{scope.resources.length} components</Chip>
        </CardHeader>
        <CardBody className="space-y-3">
          {kindCounts(scope.resources).map((counted) => (
            <Kind
              key={counted.kind}
              label={counted.label}
              count={counted.count}
              resources={scope.resources.filter(
                (resource) => resource.component.kind === counted.kind
              )}
            />
          ))}
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
          <Board board={board} project={scope.key} />
        </CardBody>
      </Card>
    </div>
  );
}

function Kind({
  label,
  count,
  resources,
}: {
  readonly label: string;
  readonly count: number;
  readonly resources: readonly CompanyBundleResource[];
}): ReactElement {
  return (
    <div>
      <div className="flex items-baseline gap-2 border-b border-line pb-1 text-xs">
        <span className="text-fg">{label}</span>
        <span className="flex-1" />
        <span className="text-muted">{count}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
        {resources.map((resource) => (
          <Mono key={`${resource.component.key}@${String(resource.component.revision)}`}>
            {pinned(resource)}
          </Mono>
        ))}
      </div>
    </div>
  );
}

/**
 * A component's key at the revision that is active, and its lifecycle when that
 * is anything other than published — a deprecated document still scoped to a
 * project is exactly the fact a person opened this panel to find.
 */
function pinned(resource: CompanyBundleResource): string {
  const at = `${resource.component.key}@${String(resource.component.revision)}`;
  return resource.component.lifecycle === "published"
    ? at
    : `${at} · ${resource.component.lifecycle}`;
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
        <span className="flex-1" />
        <span className="text-2xs text-muted">read at</span>
        <Mono
          className="text-muted"
          title={`projection ${String(view.projection_watermark)} · source ${String(view.source_watermark)}`}
        >
          {view.projection_watermark} / {view.source_watermark}
        </Mono>
      </div>
    </>
  );
}
