import type { ReactElement } from "react";
import { Card, CardHeader, CardTitle } from "../../ui/primitives";
import { spend } from "./crew";
import type { Crew } from "./crew";
import { CrewRow } from "./CrewRow";

/**
 * The crews of one project, under the name the project gave itself.
 *
 * A project is the group because a crew only exists inside one: the bundle binds
 * an agent profile to `<project>:<seat>`, and a seat credential is issued
 * against a project key. The heading is the project component's own
 * `display_name` — never the key underneath it, which is what the screen this
 * replaces printed in monospace three times over.
 *
 * The line beside the count is the one live fact this screen can state without
 * guessing. `listProjectSessions` answers per project, and every number in it is
 * the project's own, so the header is real today even while the rows' own state
 * columns are waiting on a join the contract does not carry yet. A project whose
 * read did not come back says so and takes no other project down with it.
 */
export type Work =
  | { readonly kind: "asking" }
  | { readonly kind: "refused" }
  | {
      readonly kind: "answered";
      readonly working: number;
      readonly gated: number;
      readonly tokens: number;
    };

export interface ProjectFleet {
  readonly name: string;
  readonly crews: readonly Crew[];
  readonly work: Work;
}

export function ProjectGroup({
  project,
  onOpen,
}: {
  readonly project: ProjectFleet;
  readonly onOpen: (crew: Crew) => void;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex-1 truncate">{project.name}</CardTitle>
        <span className="shrink-0 text-xs text-muted tabular-nums">
          {crews(project.crews.length)}
        </span>
        <WorkLine work={project.work} />
      </CardHeader>
      {project.crews.length === 0 ? (
        <p className="m-0 px-4 py-6 text-center text-sm text-muted">
          No crew works on {project.name} yet.
        </p>
      ) : (
        project.crews.map((crew) => <CrewRow key={crew.name} crew={crew} onOpen={onOpen} />)
      )}
    </Card>
  );
}

/**
 * What this project has running, said in the operator's own units.
 *
 * Drawn only where there is something to draw: a project with nothing at work
 * gets no line rather than a line of zeroes, because "0 working · 0 at a gate"
 * is a sentence that looks like a fault and is not one.
 */
function WorkLine({ work }: { readonly work: Work }): ReactElement | null {
  if (work.kind === "asking") {
    return <span className="shrink-0 text-xs text-muted">Asking…</span>;
  }
  if (work.kind === "refused") {
    return (
      <span className="shrink-0 text-xs text-danger">ctower did not answer for this one.</span>
    );
  }
  const said = [
    work.working === 0 ? null : `${String(work.working)} working`,
    work.gated === 0 ? null : `${String(work.gated)} at a gate`,
    work.tokens === 0 ? null : `${spend(work.tokens)} tokens today`,
  ].filter((one) => one !== null);
  return said.length === 0 ? null : (
    <span className="shrink-0 text-xs text-muted tabular-nums">{said.join(" · ")}</span>
  );
}

function crews(count: number): string {
  return count === 1 ? "1 crew" : `${String(count)} crews`;
}
