import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { PRIORITIES } from "./lanes";
import type { PriorityChoice, Project } from "./lanes";

/**
 * The two questions an operator asks a board first: whose work, and how urgent.
 *
 * They are not the same kind of control and they are not drawn as one. The
 * project is the read — the contract requires it, and choosing another one asks
 * ctower a new question. The priority narrows the answer already on screen and
 * touches the network not at all. Both are honest about which they are: the
 * project sits in a labelled select, the priority in a segment that shows what
 * it kept.
 */
export function Filters({
  projects,
  projectKey,
  onProject,
  priority,
  onPriority,
  counts,
}: {
  readonly projects: readonly Project[];
  readonly projectKey: string | null;
  readonly onProject: (key: string) => void;
  readonly priority: PriorityChoice;
  readonly onPriority: (choice: PriorityChoice) => void;
  /**
   * How many cards each choice would keep, or `null` while the board has not
   * answered. A zero drawn before the read lands is a claim about cards nobody
   * has counted, so nothing is drawn instead.
   */
  readonly counts: Readonly<Record<PriorityChoice, number>> | null;
}): ReactElement {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-4">
      <div className="flex items-center gap-2">
        <label className="text-2xs text-muted" htmlFor="board-project">
          Project
        </label>
        <select
          id="board-project"
          className={cn(
            "h-7 rounded-sm border border-line bg-bg px-2 font-mono text-xs text-fg",
            "focus:border-transparent focus:outline-2 focus:outline-offset-0 focus:outline-amber"
          )}
          value={projectKey ?? ""}
          onChange={(event): void => {
            onProject(event.target.value);
          }}
        >
          {projects.map((project) => (
            <option key={project.key} value={project.key}>
              {project.key} · {project.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-2xs text-muted">Priority</span>
        <div className="flex overflow-hidden rounded-sm border border-line">
          {PRIORITIES.map((choice) => (
            <button
              key={choice}
              type="button"
              aria-pressed={choice === priority}
              className={cn(
                "h-7 cursor-pointer border-l border-line px-2.5 text-xs first:border-l-0",
                choice === priority
                  ? "bg-amber font-semibold text-on-amber"
                  : "bg-transparent text-muted hover:bg-raised"
              )}
              onClick={(): void => {
                onPriority(choice);
              }}
            >
              {choice === "any" ? "Any" : choice}
              {counts === null ? null : (
                <span className="ml-1.5 opacity-70">{String(counts[choice])}</span>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
