import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { adapterFor } from "../harness/schema";
import type { HarnessFamily } from "./harnesses";

/**
 * The company's agents, read out of the bundle and named the way a person names
 * them.
 *
 * An agent is a profile plus the persona it points at, and the operator's word
 * for it — "Commander" — is the persona's display name. The key underneath is
 * carried here because the address needs one to reopen a screen on, and it is
 * the only field in this module that must never be drawn.
 *
 * The harness is the one join worth explaining. A profile pins a harness by
 * reference; a harness component records an `adapter`, and `harness/schema.ts`
 * declares the three adapters the runner actually binds along with the name a
 * person calls each one. So an adapter this console declares becomes a name,
 * and an adapter it does not stays honestly nameless rather than being printed
 * raw — a recorded harness whose name nobody has written down is a real state,
 * and the alternative is machine text on the screen.
 */
export interface AgentFacts {
  /** Internal. The address reopens on it; no surface draws it. */
  readonly key: string;
  readonly name: string;
  /** What a person calls the harness, when this console can name it. */
  readonly harness: string | null;
  /** The declared family, when the recorded adapter is one this console knows. */
  readonly family: HarnessFamily | null;
  readonly skills: readonly string[];
  readonly tools: readonly string[];
  /** The projects this agent holds a seat in, by the key a read takes. */
  readonly projects: readonly string[];
  /** How many seats the bundle assigns this agent to. */
  readonly seats: number;
}

export function agentsOf(document: CompanyBundleDocument): readonly AgentFacts[] {
  const personas = payloadsBy(document, "persona");
  const skills = displayNames(document, "skill");
  const tools = displayNames(document, "tool");
  const harnesses = adaptersBy(document);
  return document.resources
    .filter((resource) => resource.component.kind === "agent_profile")
    .map((resource) => {
      const adapter = harnesses.get(text(resource, "harness_ref") ?? "") ?? null;
      const declared = adapter === null ? undefined : adapterFor(adapter);
      return {
        key: resource.component.key,
        name: nameOf(personas, text(resource, "persona_ref")),
        harness: declared?.label ?? null,
        family: (declared?.key as HarnessFamily | undefined) ?? null,
        skills: named(skills, refs(resource, "skill_refs")),
        tools: named(tools, refs(resource, "tool_refs")),
        projects: projectsOf(document, resource),
        seats: seatsOf(document, resource).length,
      };
    });
}

/** The agent an address names, or nothing when it names one this company lost. */
export function agentAt(document: CompanyBundleDocument, key: string | null): AgentFacts | null {
  return key === null ? null : (agentsOf(document).find((agent) => agent.key === key) ?? null);
}

/**
 * The reference an agent created on this family would pin, when the company
 * already records a harness for it.
 *
 * The match is on the adapter the record stores, which is the same string the
 * first-run wizard writes when it connects one — a declared equality, not a
 * name that merely looks alike. Nothing here guesses: a company with no harness
 * for the chosen family gets `null`, and the flow authors one rather than
 * pinning something that is not there.
 */
export function harnessRefFor(
  document: CompanyBundleDocument,
  family: HarnessFamily
): string | null {
  const found = document.resources.find(
    (resource) =>
      resource.component.kind === "harness" && text(resource, "adapter") === (family as string)
  );
  return found === undefined ? null : `${found.component.key}@${String(found.component.revision)}`;
}

/**
 * The projects an agent works in.
 *
 * A bundle assignment's subject is `<namespace>:<name>`, and a namespace that
 * is a recorded project key names a seat in that project — the same reading the
 * cockpit's rail makes. That is the one honest join between an agent and a
 * project-scoped read; a seat key a session records is a different string and
 * joins to nothing here.
 */
function projectsOf(
  document: CompanyBundleDocument,
  resource: CompanyBundleResource
): readonly string[] {
  const keys = projectKeys(document);
  const found = new Set<string>();
  for (const subject of seatsOf(document, resource)) {
    const namespace = subject.slice(0, Math.max(subject.indexOf(":"), 0));
    if (keys.has(namespace)) {
      found.add(namespace);
    }
  }
  return [...found];
}

function seatsOf(
  document: CompanyBundleDocument,
  resource: CompanyBundleResource
): readonly string[] {
  return document.assignments
    .filter(
      (assignment) =>
        assignment.slot === "agent_profile" &&
        assignment.component.kind === resource.component.kind &&
        assignment.component.key === resource.component.key &&
        assignment.component.revision === resource.component.revision
    )
    .map((assignment) => assignment.subject);
}

function projectKeys(document: CompanyBundleDocument): ReadonlySet<string> {
  return new Set(
    document.assignments
      .map((assignment) => assignment.subject)
      .filter((subject) => subject.startsWith("project:"))
      .map((subject) => subject.slice("project:".length))
  );
}

/** Every persona payload, by the reference a profile pins it with. */
function payloadsBy(
  document: CompanyBundleDocument,
  kind: string
): ReadonlyMap<string, CompanyBundleResource> {
  const found = new Map<string, CompanyBundleResource>();
  for (const resource of document.resources) {
    if (resource.component.kind === kind) {
      found.set(`${resource.component.key}@${String(resource.component.revision)}`, resource);
    }
  }
  return found;
}

function adaptersBy(document: CompanyBundleDocument): ReadonlyMap<string, string> {
  const found = new Map<string, string>();
  for (const resource of document.resources) {
    const adapter = resource.component.kind === "harness" ? text(resource, "adapter") : null;
    if (adapter !== null) {
      found.set(`${resource.component.key}@${String(resource.component.revision)}`, adapter);
    }
  }
  return found;
}

function displayNames(document: CompanyBundleDocument, kind: string): ReadonlyMap<string, string> {
  const found = new Map<string, string>();
  for (const [reference, resource] of payloadsBy(document, kind)) {
    const name = text(resource, "display_name");
    if (name !== null) {
      found.set(reference, name);
    }
  }
  return found;
}

/**
 * A reference nothing in this bundle answers draws nothing rather than its own
 * reference: a dangling pin is a defect in the record, and printing the pin
 * would put machine text on the screen to report it.
 */
function named(
  names: ReadonlyMap<string, string>,
  references: readonly string[]
): readonly string[] {
  return references.map((reference) => names.get(reference)).filter((name) => name !== undefined);
}

function nameOf(
  personas: ReadonlyMap<string, CompanyBundleResource>,
  reference: string | null
): string {
  const found = reference === null ? undefined : personas.get(reference);
  return (found === undefined ? null : text(found, "display_name")) ?? "Unnamed";
}

function refs(resource: CompanyBundleResource, field: string): readonly string[] {
  const value = resource.payload[field];
  return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
}

function text(resource: CompanyBundleResource, field: string): string | null {
  const value = resource.payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}
