import { useCallback, useState } from "react";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import type { ReactElement } from "react";
import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { Mono } from "../ui/primitives";
import { cn } from "../ui/cn";

/**
 * The project the console is working in, under the company it belongs to.
 *
 * A company is one record with many projects in it, so the rail carries both:
 * the company that was read, and which of its projects the operator is pointed
 * at. Every row here is a `ctower.project/v1` component of the recorded bundle
 * — this switcher reads, it never authors. Creating a project is the harness
 * screen's act, and the last row goes there rather than growing a second form.
 *
 * The chip is the project's ticket prefix. The reference console shows a prefix
 * beside the thing it identifies; a ctower company has none, and a project has
 * exactly that field, so this is the one place it is the real thing to show.
 */
export interface ProjectChoice {
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
  /** Where a project is made: the harness screen. */
  readonly onAdd: () => void;
}): ReactElement {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="flex w-full cursor-pointer items-center gap-2.5 px-4 py-2.5 text-left hover:bg-raised"
        >
          <PrefixMark prefix={current?.prefix ?? null} />
          <span className="min-w-0 flex-1">
            <span className="block text-[10.5px] tracking-[0.1em] text-muted">PROJECT</span>
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
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-fg">{project.name}</span>
                  <Mono className="block truncate text-muted">{project.key}</Mono>
                </span>
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
            <span className="flex-1 truncate text-sm text-fg">Add a project…</span>
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
 * The projects this company records, in the order the bundle carries them.
 *
 * The document declares no order over its resources, so none is invented here:
 * re-sorting a list the record hands over would be this screen's claim, not the
 * record's.
 */
export function projectChoices(document: CompanyBundleDocument): readonly ProjectChoice[] {
  return document.resources
    .filter((resource) => resource.component.kind === "project")
    .map((resource) => ({
      key: resource.component.key,
      name: text(resource, "display_name") ?? resource.component.key,
      prefix: text(resource, "prefix"),
    }));
}

function text(resource: CompanyBundleResource, field: string): string | null {
  const value = resource.payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Where the console's choice of project is kept between visits. */
export const PROJECT_STORAGE_KEY = "ctower-project";

/**
 * Which project the console is on, and how it changes.
 *
 * The choice outlives a reload, because a console that forgets where it was
 * pointed is a console the operator has to re-aim every morning. A remembered
 * project that the record no longer carries is not honoured — the console
 * falls back to the first project the bundle holds and says that name, rather
 * than naming a project this company does not have.
 */
export function useCurrentProject(projects: readonly ProjectChoice[]): {
  readonly current: ProjectChoice | null;
  readonly choose: (key: string) => void;
} {
  const [chosen, setChosen] = useState<string | null>(remembered);
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

function remembered(): string | null {
  try {
    return window.localStorage.getItem(PROJECT_STORAGE_KEY);
  } catch {
    return null;
  }
}
