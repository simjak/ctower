import type { CompanyBundleDocument } from "@ctower/client";

/**
 * Which projects this console can ask the work plane about.
 *
 * The work-plane project key is **not** a company component key. The record
 * owns the rule that joins them: `allocate_ticket_display_key` matches a
 * project component by `split_part(component_key, '.', 1)`, so
 * `ctower.control-plane` is the work-plane project `ctower`. This reads that
 * rule and guesses nothing.
 *
 * No operation the authored contract declares enumerates work-plane projects,
 * so the company definition's own projects are what can be offered. Any other
 * key can still be named — the same shape `ctowerctl board query <project_key>`
 * already has.
 */
export interface WorkProject {
  /** The key the work plane answers to. */
  readonly key: string;
  /** The name a person gave it, when exactly one component carries the key. */
  readonly name: string;
}

export function workProjectsIn(document: CompanyBundleDocument): readonly WorkProject[] {
  const named = new Map<string, string | null>();
  for (const resource of document.resources) {
    if (resource.component.kind !== "project") {
      continue;
    }
    const key = workKeyOf(resource.component.key);
    const display = resource.payload.display_name;
    const name = typeof display === "string" && display.length > 0 ? display : null;
    // Two components can share a first dot-segment. They are then one
    // work-plane project with two definitions, and naming it after either one
    // would be a guess, so it keeps its key.
    named.set(key, named.has(key) ? null : name);
  }
  return [...named.entries()]
    .map(([key, name]) => ({ key, name: name ?? key }))
    .sort((left, right) => left.key.localeCompare(right.key));
}

function workKeyOf(componentKey: string): string {
  return componentKey.split(".")[0] ?? componentKey;
}
