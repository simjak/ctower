import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { Mono } from "../ui/primitives";

/**
 * Which projects this read covers.
 *
 * The options are the portfolio the last unfiltered read answered with, so the
 * control cannot offer a destination ctower did not name. Choosing one re-asks
 * `listRequests` with its single parameter — nothing here narrows rows that are
 * already held, because a filtered view of a portfolio answer would carry the
 * portfolio's epistemics while showing one project's rows.
 */
export function Scope({
  projects,
  here,
  onGo,
}: {
  readonly projects: readonly string[];
  /** The project in scope, or `null` for the whole portfolio. */
  readonly here: string | null;
  readonly onGo: (project: string | null) => void;
}): ReactElement | null {
  if (projects.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Projects">
      <Choice
        active={here === null}
        onGo={(): void => {
          onGo(null);
        }}
      >
        All
      </Choice>
      {projects.map((project) => (
        <Choice
          key={project}
          active={here === project}
          onGo={(): void => {
            onGo(project);
          }}
        >
          <Mono>{project}</Mono>
        </Choice>
      ))}
    </div>
  );
}

function Choice({
  active,
  onGo,
  children,
}: {
  readonly active: boolean;
  readonly onGo: () => void;
  readonly children: ReactElement | string;
}): ReactElement {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onGo}
      className={cn(
        "h-7 cursor-pointer rounded-sm border px-2.5 text-xs",
        active
          ? "border-amber bg-amber/14 text-amber-ink"
          : "border-line text-muted hover:bg-raised hover:text-fg"
      )}
    >
      {children}
    </button>
  );
}
