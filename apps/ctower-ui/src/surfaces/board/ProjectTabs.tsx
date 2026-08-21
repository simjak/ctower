"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import type { ReactElement } from "react";
import type { ConfiguredProject } from "@/read/projects";
import { boardHref } from "./boardHref";
import { ALL_SOURCES } from "./lanes";

/**
 * The board's primary axis: which project's board this is.
 *
 * The operator runs three projects and asked to see three boards. Source kind —
 * `dogfood-gap`, `operator-spec`, `mission-control-request`, `fixture` — is
 * provenance, not a project, and it was the top-level axis only because it was
 * the dimension the record already carried. It is still offered, one row down,
 * as a filter *within* a project.
 *
 * The list comes from `read/projects.ts`, so a fourth project appears here the
 * moment the fleet configures one, and never because someone typed it twice.
 * The choice lives in the URL like every other selection on this surface.
 */
export function ProjectTabs({
  projects,
  selected,
  lane,
}: {
  readonly projects: readonly ConfiguredProject[];
  readonly selected: string;
  /**
   * The lane the reader is narrowed to, carried across the switch. A lane is a
   * closed vocabulary every project's board answers in, so it survives; a source
   * kind is that project's own provenance and does not, which is why the source
   * resets to all rather than filtering the new board by a kind it may not hold.
   */
  readonly lane: string;
}): ReactElement {
  const router = useRouter();
  const choose = useCallback(
    (key: string): void => {
      router.push(boardHref({ project: key, source: ALL_SOURCES, lane }));
    },
    [lane, router]
  );

  return (
    <nav className="tabs" aria-label="Choose a project" style={{ flexWrap: "wrap", rowGap: "8px" }}>
      {projects.map((project) => (
        <label
          className={`tab t-${project.scopeToken}`}
          key={project.key}
          title={`the board read with project_key=${project.key}`}
        >
          <input
            type="radio"
            name="project"
            value={project.key}
            checked={project.key === selected}
            onChange={() => {
              choose(project.key);
            }}
          />
          <i className="swatch" />
          {project.key}
        </label>
      ))}
    </nav>
  );
}
