import type { ReactElement } from "react";
import { Mono } from "../ui/primitives";
import { cn } from "../ui/cn";
import type { Crew, Project } from "./roster";

/**
 * The company's crews, by the project they hold a seat in.
 *
 * The project heading is the `project_key` itself, in the machine face, because
 * that is what it is: the exact string every project-scoped read takes. The
 * bundle records display names for project *components*, and those are a
 * different key — putting one over the other would be labelling a row with a
 * name that does not identify it.
 *
 * No row carries a state mark. The bundle says who the company has; the work
 * record says what was worked on; and at this head nothing joins one to the
 * other, so no seat here has a recorded state to draw. A mark inferred from a
 * near-matching name is exactly the borrowed glyph `DESIGN.md` forbids.
 */
export function CrewRail({
  projects,
  selected,
  onSelect,
}: {
  readonly projects: readonly Project[];
  readonly selected: string | null;
  readonly onSelect: (subject: string) => void;
}): ReactElement {
  return (
    <nav aria-label="Crews" className="min-h-0 overflow-y-auto py-2">
      {projects.map((project) => (
        <div key={project.key}>
          <div className="flex items-baseline gap-2 px-3 pt-3 pb-1">
            <Mono className="min-w-0 flex-1 truncate text-muted">{project.key}</Mono>
            <span className="shrink-0 text-2xs text-muted">{project.crews.length}</span>
          </div>
          {project.crews.length === 0 ? (
            <p className="m-0 px-3 pb-1 text-2xs text-muted">No seats in this project.</p>
          ) : (
            project.crews.map((crew) => (
              <CrewRow
                key={crew.subject}
                crew={crew}
                here={crew.subject === selected}
                onSelect={onSelect}
              />
            ))
          )}
        </div>
      ))}
    </nav>
  );
}

function CrewRow({
  crew,
  here,
  onSelect,
}: {
  readonly crew: Crew;
  readonly here: boolean;
  readonly onSelect: (subject: string) => void;
}): ReactElement {
  return (
    <button
      type="button"
      aria-current={here ? "true" : undefined}
      onClick={(): void => {
        onSelect(crew.subject);
      }}
      className={cn(
        "flex w-full cursor-pointer items-baseline gap-2 px-3 py-1.5 text-left text-sm",
        here
          ? "border-r-2 border-amber bg-amber/14 font-semibold"
          : "border-r-2 border-transparent hover:bg-raised"
      )}
    >
      <span className="min-w-0 flex-1 truncate">{crew.seat}</span>
      {/* The persona is in the head of the pane this row opens, so repeating it
          down the column would be chrome. An unstaffed seat is the one thing
          the row itself has to say, because nothing downstream can say it. */}
      {crew.profileKey === null ? (
        <span className="shrink-0 text-2xs text-muted">no agent</span>
      ) : null}
    </button>
  );
}
