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
  /** The authored key that pins it. It addresses the row; it does not render. */
  readonly key: string;
  /** Where this project's code is, when the payload names a repository. */
  readonly repository: Repository | null;
  /** The seats or projects this component is bound to. */
  readonly subjects: readonly string[];
}

/**
 * A repository, as a person reads it and as a browser opens it.
 *
 * `repository:github/simjak/ctower/<40 hex>` is a host, a path, and the commit
 * the record pins. A row says the path, because that is the repository's name;
 * the link carries the pin, so following it lands on the exact commit this
 * company recorded rather than wherever that branch has since moved.
 */
export interface Repository {
  /** What the row says: `simjak/ctower`. */
  readonly label: string;
  /** Where it opens, or null when the reference names a host with no address. */
  readonly href: string | null;
  /** The host the reference names, exactly as authored. */
  readonly host: string;
  /** The reference as recorded, for the hover. */
  readonly reference: string;
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
        repository: repository === null ? null : repositoryOf(repository),
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
      return {
        id: componentId(resource.component),
        name: (persona === null ? null : (personas.get(persona) ?? null)) ?? resource.component.key,
        key: resource.component.key,
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
 * The hosts this console can turn into an address, and how each one names a
 * commit.
 *
 * A reference carries a host family — `github`, `gitlab` — and not a domain, so
 * every address below is this console's claim rather than the record's. That is
 * why the set is closed and tiny: a host that is not in it gets no link at all,
 * because the alternative is a plausible URL nobody recorded.
 */
const HOSTS: Readonly<Record<string, { readonly origin: string; readonly tree: string }>> = {
  github: { origin: "https://github.com", tree: "tree" },
  gitlab: { origin: "https://gitlab.com", tree: "-/tree" },
};

/** `repository:<host>/<path>[/<40 hex>]` split into what it actually says. */
function repositoryOf(reference: string): Repository {
  const path = reference.replace(/^repository:/, "");
  const match = /^([a-z][a-z0-9.-]*)\/(.+?)(?:\/([0-9a-f]{40}))?$/.exec(path);
  const host = match?.[1] ?? "";
  const repository = match?.[2] ?? path;
  const commit = match?.[3];
  const site = HOSTS[host];
  if (site === undefined) {
    // Nothing is invented for a host with no address: the row says the
    // reference as recorded, and says it as text.
    return { label: path, href: null, host, reference };
  }
  const pinned = commit === undefined ? "" : `/${site.tree}/${commit}`;
  return { label: repository, href: `${site.origin}/${repository}${pinned}`, host, reference };
}

/**
 * `repository:github/simjak/ctower/<40 hex>` is one fact wearing two: where the
 * code is, and which commit is pinned. The row shows both, with the commit at
 * the length a person actually reads one; the whole value stays in the hover.
 */
export function readableRepository(reference: string): string {
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
