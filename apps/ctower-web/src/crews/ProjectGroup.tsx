import type { ReactElement } from "react";
import type { ProjectSessionPage } from "@ctower/client";
import { Card, CardHeader, CardTitle } from "../ui/primitives";
import type { Answer } from "../api/client";
import { CrewRow } from "./CrewRow";
import type { ProjectCrews } from "./roster";
import { spend, workOf } from "./work";

/**
 * The crews of one project, under the name the project gave itself.
 *
 * A project is the group because a crew only exists inside one: the bundle
 * binds an agent profile to `<project>:<seat>`, and a seat credential is issued
 * against a project key. The heading is the project's own recorded name —
 * never the key underneath it, which is what the screen this replaces printed
 * in monospace three times over.
 *
 * The line beside the count is the one live fact this screen states without
 * guessing, and a project whose read did not come back says so on its own
 * header and takes no other project down with it.
 */
export function ProjectGroup({
  project,
  sessions,
}: {
  readonly project: ProjectCrews;
  readonly sessions: Answer<ProjectSessionPage>;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex-1 truncate">{project.name}</CardTitle>
        <span className="shrink-0 text-xs text-muted tabular-nums">
          {counted(project.crews.length)}
        </span>
        <WorkLine sessions={sessions} />
      </CardHeader>
      {project.crews.length === 0 ? (
        <p className="m-0 px-4 py-6 text-center text-sm text-muted">
          No crew works on {project.name} yet.
        </p>
      ) : (
        project.crews.map((crew) => <CrewRow key={crew.subject} crew={crew} />)
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
function WorkLine({ sessions }: { readonly sessions: Answer<ProjectSessionPage> }): ReactElement {
  const work = workOf(sessions);
  if (work === null) {
    return <span className="shrink-0" />;
  }
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
    work.tokens === 0 ? null : `${spend(work.tokens)} tokens`,
  ].filter((one) => one !== null);
  return said.length === 0 ? (
    <span className="shrink-0" />
  ) : (
    <span
      className="shrink-0 text-xs text-muted tabular-nums"
      title={`${work.tokens.toLocaleString()} tokens recorded`}
    >
      {said.join(" · ")}
    </span>
  );
}

function counted(crews: number): string {
  return crews === 1 ? "1 crew" : `${String(crews)} crews`;
}
