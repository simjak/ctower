import { useCallback, useState } from "react";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { cn } from "../ui/cn";
import { projectFromSearch } from "./destinations";

/**
 * The project the project workspace is about.
 *
 * It sits at the head of the section it governs: every destination under it
 * reads this project and no other, and switching here moves all of them at
 * once. Every row is a `ctower.project/v1` component of the recorded bundle —
 * this switcher reads, it never authors. Creating a project is the Projects
 * screen's act, and the last row goes there rather than growing a second form.
 *
 * The chip is the project's ticket prefix. The reference console shows a prefix
 * beside the thing it identifies; a ctower company has none, and a project has
 * exactly that field, so this is the one place it is the real thing to show.
 */
export interface ProjectChoice {
  /**
   * The work-plane key every project-addressed read takes, and the one the
   * address carries.
   */
  readonly key: string;
  /** The name the payload gave it, or its key when it named none. */
  readonly name: string;
  /** The ticket prefix, when the payload carries one. */
  readonly prefix: string | null;
}

export function ProjectSwitcher({
  projects,
  current,
  onChoose,
  onAdd,
}: {
  readonly projects: readonly ProjectChoice[];
  /** The one the console is on; null only when the company carries none. */
  readonly current: ProjectChoice | null;
  readonly onChoose: (key: string) => void;
  /** Where a project is made: the Projects screen. */
  readonly onAdd: () => void;
}): ReactElement {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          // The name of the project is what it shows; what the control *is* is
          // only knowable from the section heading above it, which somebody
          // reaching the button alone does not have.
          aria-label={`Project: ${current === null ? "None yet" : current.name}`}
          className="flex w-full cursor-pointer items-center gap-2.5 px-4 py-2.5 text-left hover:bg-raised"
        >
          <PrefixMark prefix={current?.prefix ?? null} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-fg">
              {current === null ? "None yet" : current.name}
            </span>
          </span>
          <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-muted" />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={4}
          className="z-50 w-[288px] rounded-md border border-line bg-card p-1"
        >
          <DropdownMenu.Label className="px-3 py-2 text-2xs tracking-[0.1em] text-muted">
            SWITCH PROJECT
          </DropdownMenu.Label>

          {projects.length === 0 ? (
            <p className="m-0 px-3 pb-2 text-sm text-muted">This company has no project yet.</p>
          ) : (
            projects.map((project) => (
              <DropdownMenu.Item
                key={project.key}
                onSelect={(): void => {
                  onChoose(project.key);
                }}
                className="flex cursor-pointer items-center gap-2.5 rounded-sm px-3 py-2 outline-none data-[highlighted]:bg-raised"
              >
                <PrefixMark prefix={project.prefix} />
                {/* The name and the ticket prefix, and nothing else. The key
                    that addresses this project is machine text; it travels in
                    the address bar and never onto the screen. */}
                <span className="min-w-0 flex-1 truncate text-sm text-fg">{project.name}</span>
                {project.key === current?.key ? (
                  <>
                    <Check aria-hidden className="size-3.5 shrink-0 text-ok" />
                    <span className="sr-only">current</span>
                  </>
                ) : null}
              </DropdownMenu.Item>
            ))
          )}

          <DropdownMenu.Separator className="my-1 h-px bg-line" />

          <DropdownMenu.Item
            onSelect={onAdd}
            className="flex cursor-pointer items-center gap-2.5 rounded-sm px-3 py-2 outline-none data-[highlighted]:bg-raised"
          >
            <Plus aria-hidden className="size-3.5 shrink-0 text-muted" />
            <span className="flex-1 truncate text-sm text-fg">New project…</span>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

/**
 * The prefix, in the slot the company's initial holds one line up. A project
 * whose payload carries none draws an empty square rather than a borrowed
 * letter: the prefix is the thing that identifies it, and inventing one would
 * put a made-up ticket code in the rail.
 */
function PrefixMark({ prefix }: { readonly prefix: string | null }): ReactElement {
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-6 shrink-0 place-content-center rounded-sm border border-line",
        "mono text-[9.5px] font-bold tracking-tight text-muted"
      )}
    >
      {prefix ?? ""}
    </span>
  );
}

/**
 * The projects this company records, in the order the bundle carries them, each
 * under the key that actually addresses it.
 *
 * A project is recorded twice over, under two identifier families. Its
 * **document** key is what the bundle keys the component by
 * (`ctower.control-plane`); the **work-plane** key is what every
 * project-addressed read takes (`ctower`), and it is what a scope names. The
 * record itself owns the rule that joins them — `allocate_ticket_display_key`
 * matches a project component by `split_part(component_key, '.', 1)` — so the
 * first segment is read here and nothing is guessed.
 *
 * This is the one place that join is made. The rail governs the project
 * workspace, so the key it hands out is the key the address carries and the key
 * every screen below it reads by; deriving it a second time somewhere else
 * would let two surfaces disagree about which project the operator is on.
 *
 * The document declares no order over its resources, so none is invented here:
 * re-sorting a list the record hands over would be this screen's claim, not the
 * record's. Two documents whose keys share a first segment address one project,
 * and the first the record carries is the one that names it.
 */
export function projectChoices(document: CompanyBundleDocument): readonly ProjectChoice[] {
  const found = new Map<string, ProjectChoice>();
  for (const resource of document.resources) {
    if (resource.component.kind !== "project") {
      continue;
    }
    const key = resource.component.key.split(".")[0] ?? "";
    const name = resource.payload.display_name;
    const prefix = resource.payload.prefix;
    if (key !== "" && !found.has(key)) {
      found.set(key, {
        key,
        name: typeof name === "string" && name !== "" ? name : key,
        prefix: typeof prefix === "string" && prefix !== "" ? prefix : null,
      });
    }
  }
  return [...found.values()];
}

/** Where the console's choice of project is kept between visits. */
export const PROJECT_STORAGE_KEY = "ctower-project";

/**
 * Which project the console is on, and how it changes.
 *
 * The address wins, so a screen is a link and the project someone was sent
 * survives the trip. Failing that the console remembers, because one that
 * forgets where it was pointed is one the operator has to re-aim every morning.
 * A project that the record no longer carries is not honoured either way — the
 * console falls back to the first project the bundle holds and says that name,
 * rather than naming a project this company does not have.
 */
export function useCurrentProject(projects: readonly ProjectChoice[]): {
  readonly current: ProjectChoice | null;
  readonly choose: (key: string) => void;
} {
  const [chosen, setChosen] = useState<string | null>(asked);
  const choose = useCallback((key: string): void => {
    setChosen(key);
    try {
      window.localStorage.setItem(PROJECT_STORAGE_KEY, key);
    } catch {
      /* a blocked storage partition must not break the switch itself */
    }
  }, []);
  return {
    current: projects.find((project) => project.key === chosen) ?? projects[0] ?? null,
    choose,
  };
}

function asked(): string | null {
  const address = projectFromSearch(window.location.search);
  if (address !== null) {
    return address;
  }
  try {
    return window.localStorage.getItem(PROJECT_STORAGE_KEY);
  } catch {
    return null;
  }
}
