import type { CompanyBundleDocument, CompanyBundleResource, ComponentKind } from "@ctower/client";

/**
 * An agent's files, read out of the company definition.
 *
 * The agent's files *are* these three component kinds. There is no
 * filesystem-file operation in the authored contract and this screen does not
 * invent one: a persona, a skill and a tool are the documents an agent is made
 * of, and they live in the company bundle like everything else the company
 * declares.
 *
 * Every value below is read from the payload the API returned. The readers are
 * narrow on purpose — a field that is not a string is not rendered as one — so
 * a payload that changes shape produces a missing line rather than a confident
 * wrong one.
 */
export const FILE_KINDS = ["persona", "skill", "tool"] as const;

export type FileKind = (typeof FILE_KINDS)[number];

export function isFileKind(kind: ComponentKind): kind is FileKind {
  return (FILE_KINDS as readonly ComponentKind[]).includes(kind);
}

/** A component's identity across revisions: what it is and what it is called. */
export function idOf(reference: { readonly kind: string; readonly key: string }): string {
  return `${reference.kind}:${reference.key}`;
}

/**
 * The files, in the order the three kinds are listed, then by key. The order is
 * fixed by this file and not by the document, so a re-read cannot silently
 * reshuffle the list under the operator's cursor.
 */
export function fileResources(document: CompanyBundleDocument): readonly CompanyBundleResource[] {
  return document.resources
    .filter((resource) => isFileKind(resource.component.kind))
    .toSorted(
      (left, right) =>
        order(left.component.kind) - order(right.component.kind) ||
        left.component.key.localeCompare(right.component.key)
    );
}

function order(kind: ComponentKind): number {
  return (FILE_KINDS as readonly ComponentKind[]).indexOf(kind);
}

export function resourceById(
  document: CompanyBundleDocument,
  id: string
): CompanyBundleResource | null {
  return fileResources(document).find((resource) => idOf(resource.component) === id) ?? null;
}

export function text(payload: Readonly<Record<string, unknown>>, field: string): string | null {
  const value = payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function strings(
  payload: Readonly<Record<string, unknown>>,
  field: string
): readonly string[] {
  const value = payload[field];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

/** The name a person recognises, and the key when the payload carries no name. */
export function nameOf(resource: CompanyBundleResource): string {
  return text(resource.payload, "display_name") ?? resource.component.key;
}

export interface CapabilityChoice {
  /** The `key@revision` string a payload names it by. */
  readonly ref: string;
  readonly key: string;
  readonly name: string;
}

/**
 * The capabilities this company declares, which are the only ones a file may
 * name. A capability that is not in the definition cannot be pinned to one
 * exact digest, so it is not offered — the registry's own `reference.exact`
 * check is what says so.
 */
export function capabilityChoices(document: CompanyBundleDocument): readonly CapabilityChoice[] {
  return document.resources
    .filter((resource) => resource.component.kind === "capability")
    .map((resource) => ({
      ref: `${resource.component.key}@${String(resource.component.revision)}`,
      key: resource.component.key,
      name: nameOf(resource),
    }))
    .toSorted((left, right) => left.key.localeCompare(right.key));
}

/**
 * What else this edit moves: every component that pins this one, walked to a
 * fixed point. A dependency pin is exact, so a new revision of a file is a new
 * revision of everything that names it — the operator reads that here, before
 * the plan, rather than meeting it as a refusal.
 */
export function dependentsOf(
  document: CompanyBundleDocument,
  resource: CompanyBundleResource
): readonly CompanyBundleResource[] {
  const moving = new Set<string>([idOf(resource.component)]);
  let found = true;
  while (found) {
    found = false;
    for (const candidate of document.resources) {
      const pins = candidate.component.compatibility.requires.some((required) =>
        moving.has(idOf(required))
      );
      if (pins && !moving.has(idOf(candidate.component))) {
        moving.add(idOf(candidate.component));
        found = true;
      }
    }
  }
  return document.resources.filter(
    (candidate) =>
      moving.has(idOf(candidate.component)) &&
      idOf(candidate.component) !== idOf(resource.component)
  );
}
