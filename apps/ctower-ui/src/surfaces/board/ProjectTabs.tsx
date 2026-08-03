"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import type { ReactElement } from "react";
import type { ConfiguredProject } from "@/read/projects";

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
}: {
  readonly projects: readonly ConfiguredProject[];
  readonly selected: string;
}): ReactElement {
  const router = useRouter();
  const choose = useCallback(
    (key: string): void => {
      router.push(`/board?project=${encodeURIComponent(key)}`);
    },
    [router]
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
