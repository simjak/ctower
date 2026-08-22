import type { ReactElement } from "react";
import { Mono } from "../ui/primitives";
import { cn } from "../ui/cn";
import { RAIL_SECTION } from "../shell/Rail";
import { LIST_ROW } from "./panes";
import type { Crew, Project } from "./roster";

/**
 * The company's crews, by the project they hold a seat in — the reference's
 * `Projects` tree, in the one rail, under the destinations.
 *
 * Measured off `crop-rail.png`: a project row carrying a bordered initial badge
 * whose label sits in the same column as the destinations' above it, then child
 * rows on a 40px pitch with a 32px fill inset 4 each side. The reference
 * indents its children 49 in a 254 rail; 48 holds the same 19% at 248.
 *
 * The heading says `SEATS`, not the reference's `Projects`. Merging the rails
 * put this block five rows under the destination list, and that list already
 * contains both `Projects` and `Crews` — either of the obvious labels would
 * repeat a navigation row directly above its own heading. The reference never
 * repeats a word between its nav block and its section labels either
 * (Home/Create/Search over Pinned/My workspaces/Team). `Seats` is the word this
 * surface already uses for the thing, twice, in its own empty states.
 *
 * No row carries a state mark or a diff badge. The reference's badge is its
 * most distinctive rail signal, and ctower has no diff read to fill it; nothing
 * at this head joins a seat to a recorded session either. A mark inferred from
 * a near-matching name is exactly the borrowed glyph the marks law forbids.
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
    <nav aria-label="Crews" className="pb-3">
      <div className={RAIL_SECTION}>SEATS</div>
      {projects.map((project) => (
        // A column rather than ordinary flow, so the child rows' 4px above and
        // below stay 4 and 4. In flow they are adjacent sibling margins and
        // collapse into one, which renders the 40 pitch as 36.
        <div key={project.key} className="flex flex-col pb-1">
          {/* The reference steps its tree from its nav labels to its children at
              19% of the rail. At 248 that is 38 → 48, so the project sits left
              of its seats rather than level with them. */}
          <div className="flex h-8 items-center gap-1.5 border-l-2 border-transparent px-4">
            <span
              aria-hidden
              className="grid size-4 shrink-0 place-content-center rounded-sm border border-line text-[9px] font-semibold text-muted"
            >
              {project.key.slice(0, 1).toUpperCase()}
            </span>
            <Mono className="min-w-0 flex-1 truncate text-fg">{project.key}</Mono>
            <span className="shrink-0 text-2xs text-muted">{project.crews.length}</span>
          </div>
          {project.crews.length === 0 ? (
            <p className="m-0 pt-0.5 pb-1 pl-12 text-2xs text-muted">No seats in this project.</p>
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
        LIST_ROW,
        // The 4px above and below is the rail's alone: 4 + a 32 fill + 4 is the
        // reference's 40 child pitch, and the right pane's rows on this same
        // `LIST_ROW` are measured at 32 with no gap.
        //
        // The reference's selected row is a filled grey block, not an accent
        // edge: weight and fill carry the state, never a hue.
        "my-1 w-[calc(100%-0.5rem)] cursor-pointer gap-2 pl-11 text-left text-sm",
        here ? "bg-raised font-medium text-fg" : "text-fg hover:bg-raised"
      )}
    >
      <span className="min-w-0 flex-1 truncate">{crew.seat}</span>
      {/* An unstaffed seat is the one thing the row itself has to say; the
          persona is in the head of the pane this row opens. */}
      {crew.profileKey === null ? (
        <span className="shrink-0 text-2xs text-muted">no agent</span>
      ) : null}
    </button>
  );
}
