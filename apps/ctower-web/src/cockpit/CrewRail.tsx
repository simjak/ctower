import type { ReactElement } from "react";
import { Mono } from "../ui/primitives";
import { cn } from "../ui/cn";
import { LIST_ROW } from "./panes";
import type { Crew, Project } from "./roster";

/**
 * The company's crews, by the project they hold a seat in — the reference's
 * `Projects` tree, at its own rhythm.
 *
 * Measured off `crop-rail.png`: a sentence-case muted section label (not
 * uppercase, not letter-spaced), a project row carrying a bordered initial
 * badge, then child rows on a 40px pitch with a 32px fill inset 4 each side.
 * The reference indents its children 49 in a 254 rail; this holds the same 19%
 * at 208.
 *
 * The section label says `Projects` because the tree's top level genuinely is
 * projects and that is the reference's own word. It sits one rail away from the
 * shell's `Projects` destination, which is a different screen — flagged for the
 * operator's walk rather than renamed, because renaming to dodge an adjacency
 * is the kind of judgement the parity ruling exists to stop.
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
    <nav aria-label="Crews" className="relative min-h-0 overflow-y-auto pb-3">
      <div className="flex h-9 items-center px-3">
        <span className="flex-1 text-xs text-muted">Projects</span>
      </div>
      {projects.map((project) => (
        <div key={project.key} className="pb-1">
          {/* The reference steps its tree 34 → 49 in a 254 rail. Held at 19%,
              that is 28 → 40 here, so the project sits left of its seats rather
              than level with them. */}
          <div className="flex h-8 items-center gap-1.5 px-2">
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
            <p className="m-0 pt-0.5 pb-1 pl-9 text-2xs text-muted">No seats in this project.</p>
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
        // The reference's selected row is a filled grey block, not an accent
        // edge: weight and fill carry the state, never a hue.
        "w-[calc(100%-0.5rem)] cursor-pointer gap-2 pl-9 text-left text-sm",
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
