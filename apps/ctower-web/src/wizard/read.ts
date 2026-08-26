import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { componentId, subjectsOf } from "./bundle";
import { repositoryOf } from "../repository/read";
import type { Repository } from "../repository/read";

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
  /** The authored key that pins it. It addresses the row; it does not render. */
  readonly key: string;
  /**
   * One line of supporting fact, as a person reads it: the harness an agent
   * runs on. Never a reference — a row says what a thing is, and the key that
   * pins it is what the record is keyed by.
   */
  readonly detail: string | null;
  /**
   * Where this project's code is, when the payload names a repository.
   *
   * A repository is the one supporting fact that is also a destination, so it
   * is carried as the thing it is rather than as a sentence about it: the row
   * can then draw a link a person can follow. Everything else a row supports
   * itself with is `detail`.
   */
  readonly repository: Repository | null;
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
        detail: null,
        repository: repository === null ? null : repositoryOf(repository),
        subjects: subjectsOf(document.assignments, resource),
      };
    });
}

/**
 * An agent is an authored profile plus the persona it speaks as. The persona's
 * display name is the name a person recognises, so it is resolved through the
 * profile's own `persona_ref` rather than guessed from the profile key — and
 * the harness it runs on is resolved the same way, through `harness_ref`. Both
 * references are machine text; what the row says is what each one is called.
 */
export function agentFacts(document: CompanyBundleDocument): readonly EntityFact[] {
  const personas = namesOf(document, "persona");
  const harnesses = namesOf(document, "harness");
  return document.resources
    .filter((resource) => resource.component.kind === "agent_profile")
    .map((resource) => {
      const persona = text(resource, "persona_ref");
      const harness = text(resource, "harness_ref");
      return {
        id: componentId(resource.component),
        name: (persona === null ? null : (personas.get(persona) ?? null)) ?? "Unnamed",
        key: resource.component.key,
        detail: harness === null ? null : (harnesses.get(harness) ?? null),
        repository: null,
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

/** What one kind of component is called, under the reference a payload pins it by. */
function namesOf(document: CompanyBundleDocument, kind: string): ReadonlyMap<string, string> {
  const names = new Map<string, string>();
  for (const resource of document.resources) {
    if (resource.component.kind !== kind) {
      continue;
    }
    const name = text(resource, "display_name");
    if (name !== null) {
      names.set(`${resource.component.key}@${String(resource.component.revision)}`, name);
    }
  }
  return names;
}

function text(resource: CompanyBundleResource, field: string): string | null {
  const value = resource.payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}
