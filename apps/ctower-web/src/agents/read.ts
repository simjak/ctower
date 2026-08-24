import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { harnessNamed } from "./harnesses";
import type { HarnessFamily } from "./harnesses";
import type { AgentStatus } from "./status";

/**
 * The agents this company records, as people rather than as components.
 *
 * An agent is authored twice over: a `persona` carries the name it speaks
 * under, and an `agent_profile` pairs that persona with the harness it runs on.
 * Neither reference renders. The profile's `persona_ref` is resolved to the
 * name a person recognises, and its `harness_ref` to that harness's adapter,
 * which `harnesses.ts` turns into words somebody says out loud.
 *
 * One reader serves the rail, the list and an agent's own home, the way
 * `projects/read.ts` serves a card and the screen behind it. Two readers over
 * one bundle is how a name in the rail and a name on the page start disagreeing
 * about who works here.
 *
 * **What the record does not keep, this does not invent.** There is no job
 * title on a persona, no model on a profile, and nothing ties a recorded run to
 * an agent — the schemas are closed (`additionalProperties: false`) and none of
 * the three fields exists. So `role`, `model`, `lastActive` and `status` come
 * back empty and the screen says once, in one line, what is missing. A row that
 * filled them from a near-enough field would be the console making up staff.
 *
 * The order is the record's. The export is normalized and deterministic
 * (`SPEC.md`, § CompanyBundle), so an agent appears where the company's own
 * record puts it; sorting here would overrule the record with a rule no
 * authored document declares.
 */
export interface AgentFacts {
  /** The key that addresses this agent. It travels; it does not render. */
  readonly key: string;
  readonly name: string;
  /** The job, in the operator's words: "Chief of staff · CEO". */
  readonly role: string | null;
  /** Plain product names, both of them: "claude-fable-5", "Claude Code". */
  readonly model: string | null;
  /** What a person calls the harness, when this console can name it. */
  readonly harness: string | null;
  /** When this agent last did something, or nothing recorded yet. */
  readonly lastActive: string | null;
  /** The recorded state, or nothing recorded yet. */
  readonly status: AgentStatus | null;
  /** What this agent holds out of the company's catalogue, by name. */
  readonly skills: readonly string[];
  readonly tools: readonly string[];
  /** The projects this agent holds a seat in, by the key a read takes. */
  readonly projects: readonly string[];
  /** How many seats the bundle assigns this agent to. */
  readonly seats: number;
}

export function agentsIn(document: CompanyBundleDocument): readonly AgentFacts[] {
  const personas = displayNames(document, "persona");
  const skills = displayNames(document, "skill");
  const tools = displayNames(document, "tool");
  const adapters = namedBy(document, "harness", "adapter");
  return document.resources
    .filter((resource) => resource.component.kind === "agent_profile")
    .map((resource) => ({
      key: resource.component.key,
      // A profile whose persona is not in this bundle has no name here. The key
      // would be one, and printing it is the thing this screen exists to stop,
      // so the row says the one true thing instead.
      name: named(personas, text(resource, "persona_ref")) ?? "Unnamed",
      role: null,
      model: null,
      harness: harnessNamed(named(adapters, text(resource, "harness_ref"))),
      lastActive: null,
      status: null,
      skills: allNamed(skills, refs(resource, "skill_refs")),
      tools: allNamed(tools, refs(resource, "tool_refs")),
      projects: projectsOf(document, resource),
      seats: seatsOf(document, resource).length,
    }));
}

/** The agent an address names, or nothing when it names one this company lost. */
export function agentAt(document: CompanyBundleDocument, key: string | null): AgentFacts | null {
  return key === null ? null : (agentsIn(document).find((agent) => agent.key === key) ?? null);
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
  return found === undefined ? null : reference(found);
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

/** What one field of one kind of component says, under the reference that pins it. */
function namedBy(
  document: CompanyBundleDocument,
  kind: string,
  field: string
): ReadonlyMap<string, string> {
  const found = new Map<string, string>();
  for (const resource of document.resources) {
    if (resource.component.kind !== kind) {
      continue;
    }
    const value = text(resource, field);
    if (value !== null) {
      found.set(reference(resource), value);
    }
  }
  return found;
}

function displayNames(document: CompanyBundleDocument, kind: string): ReadonlyMap<string, string> {
  return namedBy(document, kind, "display_name");
}

function named(names: ReadonlyMap<string, string>, reference: string | null): string | null {
  return reference === null ? null : (names.get(reference) ?? null);
}

/**
 * A reference nothing in this bundle answers draws nothing rather than its own
 * reference: a dangling pin is a defect in the record, and printing the pin
 * would put machine text on the screen to report it.
 */
function allNamed(
  names: ReadonlyMap<string, string>,
  references: readonly string[]
): readonly string[] {
  return references.map((held) => names.get(held)).filter((name) => name !== undefined);
}

function reference(resource: CompanyBundleResource): string {
  return `${resource.component.key}@${String(resource.component.revision)}`;
}

function refs(resource: CompanyBundleResource, field: string): readonly string[] {
  const value = resource.payload[field];
  return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
}

function text(resource: CompanyBundleResource, field: string): string | null {
  const value = resource.payload[field];
  return typeof value === "string" && value.length > 0 ? value : null;
}
