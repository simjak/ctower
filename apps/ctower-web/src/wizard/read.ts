import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { componentId, subjectsOf } from "./bundle";

/**
 * What a row on the form actually says.
 *
 * Every value here is read out of the authored payload the API returned. The
 * reader is deliberately narrow — a field that is not a string is not rendered
 * as one — so a payload that changes shape produces a missing line rather than
 * a confident wrong one.
 */
export interface EntityFact {
  readonly id: string;
  /** The name a person gave this thing, when the payload carries one. */
  readonly name: string;
  /** The authored key that pins it. */
  readonly key: string;
  /** One line of supporting fact: a repository, a harness, a persona. */
  readonly detail: string | null;
  /** The full value behind `detail`, for the hover. */
  readonly detailTitle: string | null;
  /** The seats or projects this component is bound to. */
  readonly subjects: readonly string[];
}

export function projectFacts(document: CompanyBundleDocument): readonly EntityFact[] {
  return document.resources
    .filter((resource) => resource.component.kind === "project")
    .map((resource) => {
      const repository = text(resource, "repository_ref");
      return {
        id: componentId(resource.component),
        name: text(resource, "display_name") ?? resource.component.key,
        key: resource.component.key,
        detail: repository === null ? null : readableRepository(repository),
        detailTitle: repository,
        subjects: subjectsOf(document.assignments, resource),
      };
    });
}

/**
 * An agent is an authored profile plus the persona it speaks as. The persona's
 * display name is the name a person recognises, so it is resolved through the
 * profile's own `persona_ref` rather than guessed from the profile key.
 */
export function agentFacts(document: CompanyBundleDocument): readonly EntityFact[] {
  const personas = personaNames(document);
  return document.resources
    .filter((resource) => resource.component.kind === "agent_profile")
    .map((resource) => {
      const persona = text(resource, "persona_ref");
      const harness = text(resource, "harness_ref");
      return {
        id: componentId(resource.component),
        name: (persona === null ? null : (personas.get(persona) ?? null)) ?? resource.component.key,
        key: resource.component.key,
        detail: harness,
        detailTitle: harness,
        subjects: subjectsOf(document.assignments, resource),
      };
    });
}

/** Everything the company is otherwise made of, counted by kind. */
export function componentCounts(
  document: CompanyBundleDocument
): readonly { readonly kind: string; readonly count: number }[] {
  const counts = new Map<string, number>();
  for (const resource of document.resources) {
    const kind = resource.component.kind;
    if (kind === "project" || kind === "agent_profile") {
      continue;
    }
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([kind, count]) => ({ kind: kind.replace(/_/g, " "), count }))
    .sort((left, right) => right.count - left.count || left.kind.localeCompare(right.kind));
}

function personaNames(document: CompanyBundleDocument): ReadonlyMap<string, string> {
  const names = new Map<string, string>();
  for (const resource of document.resources) {
    if (resource.component.kind !== "persona") {
      continue;
    }
    const name = text(resource, "display_name");
    if (name !== null) {
      names.set(`${resource.component.key}@${String(resource.component.revision)}`, name);
    }
  }
  return names;
}

/**
 * `repository:github/simjak/ctower/<40 hex>` is one fact wearing two: where the
 * code is, and which commit is pinned. The row shows both, with the commit at
 * the length a person actually reads one; the whole value stays in the hover.
 */
function readableRepository(reference: string): string {
  const path = reference.replace(/^repository:/, "");
  const match = /^(.*)\/([0-9a-f]{40})$/.exec(path);
  if (match === null) {
    return path;
  }
  return `${match[1] ?? path} @ ${(match[2] ?? "").slice(0, 7)}`;
}

function text(resource: CompanyBundleResource, field: string): string | null {
  const value = resource.payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}
