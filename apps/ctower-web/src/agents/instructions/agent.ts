import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { idOf, nameOf } from "./read";

/**
 * One agent's instructions, read out of the profile that declares them.
 *
 * The harness screen listed every file the company carried, because a harness
 * has no opinion about which agent reads what. An agent does: its profile names
 * the persona it speaks as, the skills it may use and the tools it may reach,
 * and those three lists *are* the answer to "what is this agent told". So this
 * module resolves them instead of showing the company's whole shelf and letting
 * the operator work out which rows belong to whom.
 *
 * The persona is the entry. Nothing in the record marks it as such — the mark
 * is what `persona_ref` means: exactly one of them, named on its own field,
 * carrying the voice the agent speaks in. A skill and a tool are things it may
 * reach for; the persona is what it is.
 *
 * References are matched by key and not by `key@revision`. A bundle carries one
 * revision of each component, so the revision in a pointer says which revision
 * the profile was authored against and never which file this is. A profile left
 * on an earlier revision still names the same file, and the editor is where
 * that gap is stated — `staleNamersOf` in `read.ts` is what says it out loud.
 */
export type Role = "entry" | "skill" | "tool";

export interface AgentFile {
  /** `kind:key`, the same identity `read.ts` opens a file by. Never rendered. */
  readonly id: string;
  readonly name: string;
  readonly role: Role;
}

export interface Agent {
  /** The name a person calls this agent, resolved through its own persona. */
  readonly name: string;
  readonly files: readonly AgentFile[];
}

/**
 * The agent this profile key names, or `null` when the company carries no such
 * profile. `null` is a real answer — an address can outlive the thing it
 * addressed — and the screen says so rather than rendering an empty shelf.
 */
export function agentIn(document: CompanyBundleDocument, profileKey: string): Agent | null {
  const profile = document.resources.find(
    (resource) =>
      resource.component.kind === "agent_profile" && resource.component.key === profileKey
  );
  if (profile === undefined) {
    return null;
  }
  const persona = named(document, "persona", ref(profile.payload.persona_ref));
  return {
    name: persona === null ? "Unnamed" : nameOf(persona),
    files: [
      ...file(persona, "entry"),
      ...refs(profile.payload.skill_refs).flatMap((key) =>
        file(named(document, "skill", key), "skill")
      ),
      ...refs(profile.payload.tool_refs).flatMap((key) =>
        file(named(document, "tool", key), "tool")
      ),
    ],
  };
}

/** One row, or none at all when the profile names something the bundle lost. */
function file(resource: CompanyBundleResource | null, role: Role): readonly AgentFile[] {
  return resource === null ? [] : [{ id: idOf(resource.component), name: nameOf(resource), role }];
}

function named(
  document: CompanyBundleDocument,
  kind: string,
  key: string | null
): CompanyBundleResource | null {
  if (key === null) {
    return null;
  }
  return (
    document.resources.find(
      (resource) => resource.component.kind === kind && resource.component.key === key
    ) ?? null
  );
}

/** The key inside a `key@revision` pointer, or the whole string when it is bare. */
function ref(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? (value.split("@")[0] ?? null) : null;
}

function refs(value: unknown): readonly string[] {
  return Array.isArray(value) ? value.map(ref).filter((key): key is string => key !== null) : [];
}
