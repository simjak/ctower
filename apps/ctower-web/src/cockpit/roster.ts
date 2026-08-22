import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";

/**
 * Who the company's crews are, read out of the bundle and nothing else.
 *
 * A bundle assignment's subject is `<namespace>:<name>`. Two namespaces are
 * load-bearing here and both are recorded facts rather than conventions:
 *
 * - `project:<key>` names a project the tower addresses. That `<key>` is
 *   literally the `project_key` every project-scoped read takes, so the rail
 *   never has to guess one from a component key — and a project component's own
 *   key (`ctower.control-plane`) is a different string that no read accepts.
 * - `<project key>:<seat>` names a crew seat inside one of those projects. A
 *   subject whose namespace is not a known project key is not a crew and does
 *   not render as one; `principal:commander` is a principal, not a seat.
 *
 * Everything a crew row says about itself — its persona's name, the harness it
 * runs on — comes from the agent profile the bundle assigns to that exact
 * subject. A seat with no profile renders as a seat with no profile.
 */
export interface Crew {
  readonly projectKey: string;
  readonly seat: string;
  /** The bundle's own subject, `<project key>:<seat>`. */
  readonly subject: string;
  /** The name a person recognises, when a persona records one. */
  readonly personaName: string | null;
  readonly harnessRef: string | null;
  readonly profileKey: string | null;
}

export interface Project {
  readonly key: string;
  readonly crews: readonly Crew[];
}

const PROJECT_NAMESPACE = "project";

export function rosterOf(document: CompanyBundleDocument): readonly Project[] {
  const keys = projectKeys(document);
  const seats = new Map<string, Crew[]>([...keys].map((key) => [key, []]));
  for (const subject of subjects(document)) {
    const crew = crewAt(document, subject, keys);
    if (crew !== null) {
      seats.get(crew.projectKey)?.push(crew);
    }
  }
  return [...keys]
    .sort((left, right) => left.localeCompare(right))
    .map((key) => ({
      key,
      crews: (seats.get(key) ?? []).sort((left, right) => left.seat.localeCompare(right.seat)),
    }));
}

export function crewCount(projects: readonly Project[]): number {
  return projects.reduce((total, project) => total + project.crews.length, 0);
}

/** The first crew the rail draws, so the cockpit opens on something real. */
export function firstCrew(projects: readonly Project[]): Crew | null {
  for (const project of projects) {
    const crew = project.crews[0];
    if (crew !== undefined) {
      return crew;
    }
  }
  return null;
}

export function findCrew(projects: readonly Project[], subject: string | null): Crew | null {
  if (subject === null) {
    return null;
  }
  for (const project of projects) {
    const found = project.crews.find((crew) => crew.subject === subject);
    if (found !== undefined) {
      return found;
    }
  }
  return null;
}

function projectKeys(document: CompanyBundleDocument): ReadonlySet<string> {
  const keys = new Set<string>();
  for (const subject of subjects(document)) {
    const split = splitSubject(subject);
    if (split !== null && split.namespace === PROJECT_NAMESPACE) {
      keys.add(split.name);
    }
  }
  return keys;
}

function subjects(document: CompanyBundleDocument): readonly string[] {
  return [...new Set(document.assignments.map((assignment) => assignment.subject))];
}

function crewAt(
  document: CompanyBundleDocument,
  subject: string,
  keys: ReadonlySet<string>
): Crew | null {
  const split = splitSubject(subject);
  if (split === null || !keys.has(split.namespace)) {
    return null;
  }
  const profile = profileFor(document, subject);
  const personaRef = profile === null ? null : text(profile, "persona_ref");
  return {
    projectKey: split.namespace,
    seat: split.name,
    subject,
    personaName: personaRef === null ? null : (personaNames(document).get(personaRef) ?? null),
    harnessRef: profile === null ? null : text(profile, "harness_ref"),
    profileKey: profile?.component.key ?? null,
  };
}

function profileFor(
  document: CompanyBundleDocument,
  subject: string
): CompanyBundleResource | null {
  const assigned = document.assignments.find(
    (assignment) => assignment.subject === subject && assignment.slot === "agent_profile"
  );
  if (assigned === undefined) {
    return null;
  }
  return (
    document.resources.find(
      (resource) =>
        resource.component.kind === assigned.component.kind &&
        resource.component.key === assigned.component.key &&
        resource.component.revision === assigned.component.revision
    ) ?? null
  );
}

/** A persona reference is `<key>@<revision>`, which is how the bundle pins one. */
function personaNames(document: CompanyBundleDocument): ReadonlyMap<string, string> {
  const names = new Map<string, string>();
  for (const resource of document.resources) {
    const name = resource.component.kind === "persona" ? text(resource, "display_name") : null;
    if (name !== null) {
      names.set(`${resource.component.key}@${String(resource.component.revision)}`, name);
    }
  }
  return names;
}

function splitSubject(subject: string): { namespace: string; name: string } | null {
  const at = subject.indexOf(":");
  if (at <= 0 || at === subject.length - 1) {
    return null;
  }
  return { namespace: subject.slice(0, at), name: subject.slice(at + 1) };
}

function text(resource: CompanyBundleResource, field: string): string | null {
  const value = resource.payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}
