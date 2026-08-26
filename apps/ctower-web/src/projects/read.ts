import type { CompanyBundleDocument, CompanyBundleResource, ComponentKind } from "@ctower/client";
import { repositoryOf } from "../repository/read";
import type { Repository } from "../repository/read";

/**
 * What the active bundle records about a project.
 *
 * A project is recorded twice over. Its **document** is a `project` component —
 * a name, a repository, a ticket prefix, the goals it serves. Its **scope** is
 * what every other component declares itself to belong to, and it is the
 * identifier every project-addressed read takes. The record's own rule joins
 * them: `allocate_ticket_display_key` matches a project component by
 * `split_part(component_key, '.', 1)`, so a document keyed `acme.delivery` is
 * the project addressed as `acme`.
 *
 * The rail makes that join once, in `shell/ProjectSwitcher`, and hands out the
 * addressing key. This reader takes it back and gathers everything under it, so
 * a card and the screen behind it agree about which project they are about.
 *
 * The order is the record's. The export is normalized and deterministic
 * (`SPEC.md`, § CompanyBundle): components are stored sorted by kind, key,
 * revision and digest, and the export replays that sequence, so a project
 * appears where the company's own record puts it.
 */
export interface ProjectFacts {
  /** The key that addresses this project. It travels; it does not render. */
  readonly key: string;
  readonly name: string;
  /** The ticket prefix — `null` when the recorded payload carries none. */
  readonly prefix: string | null;
  /** Where this project's code is; `null` when the record names no repository. */
  readonly repository: Repository | null;
  /** The goals this project serves, named where the bundle names them. */
  readonly goals: readonly string[];
  /** Everything this company records under this project. */
  readonly scoped: readonly CompanyBundleResource[];
}

/** How many of one kind of component a project holds, and what they are called. */
export interface KindCount {
  readonly kind: ComponentKind;
  /** The kind as a person reads it; the payload's own word, unpunctuated. */
  readonly label: string;
  readonly count: number;
  /** The names those components carry, for the ones that carry a name. */
  readonly names: readonly string[];
}

export function projectsIn(document: CompanyBundleDocument): readonly ProjectFacts[] {
  const goals = goalNames(document);
  const found = new Map<string, ProjectFacts>();
  for (const resource of document.resources) {
    const key = resource.component.key.split(".")[0] ?? "";
    if (resource.component.kind !== "project" || key === "" || found.has(key)) {
      continue;
    }
    const repository = text(resource, "repository_ref");
    found.set(key, {
      key,
      name: text(resource, "display_name") ?? resource.component.key,
      prefix: text(resource, "prefix"),
      repository: repository === null ? null : repositoryOf(repository),
      goals: goalRefs(resource).map((reference) => goals.get(reference) ?? "an unrecorded goal"),
      scoped: document.resources.filter((held) => held.component.scope.project === key),
    });
  }
  return [...found.values()];
}

/**
 * A project's components counted by kind, in the order the export gave the
 * kinds. Same rule as the list itself: the export is ordered by kind first, so
 * the groups arrive already grouped and already sequenced. Ranking them by size
 * would be a second answer to a question the record has already answered.
 */
export function kindCounts(resources: readonly CompanyBundleResource[]): readonly KindCount[] {
  const counts = new Map<ComponentKind, CompanyBundleResource[]>();
  for (const resource of resources) {
    const held = counts.get(resource.component.kind) ?? [];
    held.push(resource);
    counts.set(resource.component.kind, held);
  }
  return [...counts.entries()].map(([kind, held]) => ({
    kind,
    label: kind.replace(/_/g, " "),
    count: held.length,
    names: held
      .map((resource) => text(resource, "display_name"))
      .filter((name): name is string => name !== null),
  }));
}

/**
 * The goal documents in the same bundle, under the exact reference a project's
 * `goal_refs` pins. A reference that resolves to nothing is said to be
 * unrecorded rather than rendered as its own machine text.
 */
function goalNames(document: CompanyBundleDocument): ReadonlyMap<string, string> {
  const names = new Map<string, string>();
  for (const resource of document.resources) {
    const name = text(resource, "display_name");
    if (resource.component.kind === "goal" && name !== null) {
      names.set(`${resource.component.key}@${String(resource.component.revision)}`, name);
    }
  }
  return names;
}

/** The goals this company records, as the references a payload pins them by. */
export function goalRefsIn(document: CompanyBundleDocument): readonly string[] {
  return document.resources
    .filter((resource) => resource.component.kind === "goal")
    .map((resource) => `${resource.component.key}@${String(resource.component.revision)}`);
}

function goalRefs(resource: CompanyBundleResource): readonly string[] {
  const value = resource.payload.goal_refs;
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function text(resource: CompanyBundleResource, field: string): string | null {
  const value = resource.payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}
