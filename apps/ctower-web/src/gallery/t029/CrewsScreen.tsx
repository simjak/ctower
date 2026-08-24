import { useState } from "react";
import type { ReactElement } from "react";
import { UserPlus } from "lucide-react";
import { Button, Card, PageHead } from "../../ui/primitives";
import { cn } from "../../ui/cn";
import { atWork } from "./crew";
import type { Crew, Standing } from "./crew";
import { ProjectGroup } from "./ProjectGroup";
import type { ProjectFleet } from "./ProjectGroup";

/**
 * The Crews screen: who works for this company, by the project they work in.
 *
 * The screen this replaces was a three-pane cockpit whose two live panes could
 * not be filled — a rail of monospace project keys, no seats, and an empty state
 * pointing at a page that could not make one either. This is a list, because a
 * list is what a roster is, and because every column in it is either a fact the
 * record already answers or an absence drawn as one.
 *
 * The bands are the operator's own fleet reading and are computed from the rows
 * rather than from a read: a band with nothing in it is not drawn, so a company
 * with nothing stuck never sees the word.
 */
export type Band = "all" | "at work" | "idle" | "stuck";

/** The bands, and the one word each is called by. Order is the reading order. */
const BANDS: readonly (readonly [Band, string])[] = [
  ["all", "All"],
  ["at work", "At work"],
  ["idle", "Idle"],
  ["stuck", "Stuck"],
];

export function CrewsScreen({
  projects,
  onNew,
  onOpen,
}: {
  readonly projects: readonly ProjectFleet[];
  readonly onNew: () => void;
  readonly onOpen: (crew: Crew) => void;
}): ReactElement {
  const [band, setBand] = useState<Band>("all");
  const total = projects.reduce((count, project) => count + project.crews.length, 0);
  const shown = projects.map((project) => ({
    ...project,
    crews: project.crews.filter((crew) => inBand(crew.standing, band)),
  }));

  return (
    <>
      <PageHead title="Crews" subtitle={across(total, projects.length) ?? undefined}>
        <Button variant="primary" onClick={onNew}>
          <UserPlus /> New crew
        </Button>
      </PageHead>
      {total === 0 ? (
        <Card className="grid place-content-center px-6 py-12 text-center">
          <p className="m-0 text-sm text-muted">This company records no crew yet.</p>
        </Card>
      ) : (
        <>
          <Bands band={band} onBand={setBand} />
          <div className="space-y-4">
            {shown.map((project) => (
              <ProjectGroup key={project.name} project={project} onOpen={onOpen} />
            ))}
          </div>
        </>
      )}
    </>
  );
}

function Bands({
  band,
  onBand,
}: {
  readonly band: Band;
  readonly onBand: (band: Band) => void;
}): ReactElement {
  return (
    <div role="tablist" className="mb-4 flex gap-1 border-b border-line">
      {BANDS.map(([one, label]) => (
        <button
          key={one}
          type="button"
          role="tab"
          aria-selected={one === band}
          onClick={(): void => {
            onBand(one);
          }}
          className={cn(
            "cursor-pointer border-b-2 border-transparent px-3 py-2 text-xs font-semibold",
            "text-muted hover:text-fg focus:outline-2 focus:outline-offset-[-2px] focus:outline-amber",
            one === band && "border-b-amber text-fg"
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/**
 * Which band a crew reads into.
 *
 * `unseen` is deliberately in neither `at work` nor `idle`. A crew no run names
 * is not resting — the record simply has not said, and sorting an unknown into a
 * known band is the same error as drawing it a borrowed mark.
 */
function inBand(standing: Standing, band: Band): boolean {
  if (band === "all") {
    return true;
  }
  if (band === "at work") {
    return atWork(standing);
  }
  if (band === "stuck") {
    return standing === "blocked" || standing === "failed";
  }
  return standing === "gated" || standing === "delivered" || standing === "abandoned";
}

/**
 * How many, and where — or nothing at all.
 *
 * A company with no crew gets no count. "0 crews across 0 projects" is a true
 * sentence that reads as a broken one, and the empty state below already says
 * the same thing in words a person would use.
 */
function across(crews: number, projects: number): string | null {
  if (crews === 0) {
    return null;
  }
  const one = crews === 1 ? "1 crew" : `${String(crews)} crews`;
  return projects === 1 ? `${one} in 1 project` : `${one} across ${String(projects)} projects`;
}
