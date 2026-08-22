import type { CompanyBundleDocument, CompanyBundleResource, ComponentKind } from "@ctower/client";
import { readableRepository } from "../wizard/read";

/**
 * What the active bundle records about projects, and it records two things that
 * are not the same thing.
 *
 * A **scope** is the project every component declares itself to belong to —
 * `component.scope.project` — and it is the identifier every project-addressed
 * read on this API takes. A **document** is a `project` component: a name, a
 * repository, a ticket prefix, the goals it serves.
 *
 * Nothing in the bundle binds one to the other. `ctower.control-plane` is a
 * document key and `ctower` is a scope; they resemble each other and a
 * resemblance is not a recorded fact, so this reader never joins them and the
 * screen draws them as the two separate things they are.
 */

/** One project components are scoped to, and everything scoped to it. */
export interface ProjectScope {
  readonly key: string;
  readonly resources: readonly CompanyBundleResource[];
}

/** How many of one kind of component a scope holds. */
export interface KindCount {
  readonly kind: ComponentKind;
  /** The kind as a person reads it; the payload's own word, unpunctuated. */
  readonly label: string;
  readonly count: number;
}

/** An authored project document, exactly as the bundle carries it. */
export interface ProjectDocument {
  readonly id: string;
  readonly key: string;
  readonly name: string;
  readonly revision: number;
  /** The ticket prefix — `null` when the recorded payload carries none. */
  readonly prefix: string | null;
  /** The repository, at the length a person reads one. */
  readonly repository: string | null;
  /** The whole reference behind it, for the hover. */
  readonly repositoryTitle: string | null;
  /** The goals this project serves, named where the bundle names them. */
  readonly goals: readonly string[];
}

/**
 * Every project scope in the bundle, in the order the export gave them.
 *
 * The record has an order and this screen does not overrule it. `SPEC.md`
 * (§ CompanyBundle, "export is normalized and deterministic") makes the export
 * order part of the answer rather than an accident of transport: the kernel
 * sorts resources by kind, key, revision and digest before an apply is stored,
 * and the export replays that stored sequence. So a scope appears here where the
 * company's own record puts it, and two reads of one bundle always agree.
 *
 * Nothing is filtered and nothing is re-ranked: every non-null scope renders,
 * once, in that order.
 */
export function projectScopes(document: CompanyBundleDocument): readonly ProjectScope[] {
  const keys = new Set(
    document.resources
      .map((resource) => resource.component.scope.project)
      .filter((key): key is string => key !== null)
  );
  return [...keys].map((key) => ({
    key,
    resources: document.resources.filter((resource) => resource.component.scope.project === key),
  }));
}

/**
 * A scope's components counted by kind, in the order the export gave the kinds.
 *
 * Same rule as `projectScopes`: the export is ordered by kind first, so the
 * groups arrive already grouped and already sequenced, and counting them keeps
 * that sequence. Ranking them by size would be a second answer to a question the
 * record has already answered, and picking a different order for an operator's
 * eye is an authored decision, not one this screen may make on its own.
 */
export function kindCounts(resources: readonly CompanyBundleResource[]): readonly KindCount[] {
  const counts = new Map<ComponentKind, number>();
  for (const resource of resources) {
    const kind = resource.component.kind;
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return [...counts.entries()].map(([kind, count]) => ({
    kind,
    label: kind.replace(/_/g, " "),
    count,
  }));
}

export function projectDocuments(document: CompanyBundleDocument): readonly ProjectDocument[] {
  const goals = goalNames(document);
  return document.resources
    .filter((resource) => resource.component.kind === "project")
    .map((resource) => {
      const repository = text(resource, "repository_ref");
      return {
        id: `${resource.component.key}@${String(resource.component.revision)}`,
        key: resource.component.key,
        name: text(resource, "display_name") ?? resource.component.key,
        revision: resource.component.revision,
        prefix: text(resource, "prefix"),
        repository: repository === null ? null : readableRepository(repository),
        repositoryTitle: repository,
        goals: goalRefs(resource).map((reference) => goals.get(reference) ?? reference),
      };
    });
}

/**
 * The goal documents in the same bundle, under the exact `key@revision` a
 * project's `goal_refs` pins. A reference that resolves to nothing keeps its own
 * text rather than borrowing a name from a goal that only looks similar.
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
