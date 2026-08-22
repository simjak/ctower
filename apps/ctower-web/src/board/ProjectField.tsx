import type { ReactElement, SyntheticEvent } from "react";
import { useState } from "react";
import { Input } from "../ui/primitives";
import type { Project } from "./lanes";

/**
 * Which project this board reads, and why the operator can name one.
 *
 * ctower has no operation that enumerates work-plane projects, so this console
 * cannot offer a closed list without inventing one. It offers what is real: the
 * projects the company's own definition names, and a field for a key the
 * definition does not — which is the shape `ctowerctl board query <project_key>`
 * already has. The key is machine-owned text, so it is set in the machine's
 * typeface.
 *
 * Typing commits on `Enter`, not per keystroke: a half-typed key is a key the
 * contract refuses, and a read per character would draw three refusals on the
 * way to one answer.
 */
export function ProjectField({
  projectKey,
  projects,
  onChoose,
}: {
  readonly projectKey: string | null;
  readonly projects: readonly Project[];
  readonly onChoose: (key: string) => void;
}): ReactElement {
  const [typed, setTyped] = useState(projectKey ?? "");

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(event: SyntheticEvent<HTMLFormElement>): void => {
        event.preventDefault();
        const next = typed.trim();
        if (next !== "") {
          onChoose(next);
        }
      }}
    >
      <label className="text-2xs text-muted" htmlFor="board-project">
        Project
      </label>
      <Input
        id="board-project"
        list="board-projects"
        autoComplete="off"
        spellCheck={false}
        placeholder="key"
        className="h-7 w-40 font-mono text-xs"
        value={typed}
        onChange={(event): void => {
          const next = event.target.value;
          setTyped(next);
          if (projects.some((project) => project.key === next)) {
            onChoose(next);
          }
        }}
      />
      <datalist id="board-projects">
        {projects.map((project) => (
          <option key={project.key} value={project.key} label={project.name} />
        ))}
      </datalist>
    </form>
  );
}
