import type { CompanyBundleDocument } from "@ctower/client";
import { canonicalDigest } from "../mint/digest";
import { resourceOf } from "../mint/component";
import type { Authoring } from "../wizard/ceremony";
import { harnessChoices } from "./harnesses";
import type { HarnessFamily } from "./harnesses";
import { harnessRefFor } from "./read";
import {
  keyPattern,
  NAME_LENGTH,
  NOT_EXERCISED,
  PERSONA_SCHEMA_REF,
  PROFILE_SCHEMA_REF,
} from "./schema";

/**
 * An agent being written, and what the record will make of it.
 *
 * The operator answers two things: what this agent is called, and which harness
 * it runs on. Everything the record insists on beyond that is derived — the key
 * both halves are stored under, the pinned reference from the profile to its
 * persona, the digest over what was actually typed — because none of those is a
 * decision. They are the same two answers spelled the way the record spells
 * them, and asking someone to spell them again is how a form starts refusing
 * good answers.
 *
 * The derivation runs on every keystroke and is checked against the authored
 * schemas before anything is proposed, so Review is downstream of `problems`
 * being empty and a payload the kernel would refuse is never sent.
 */
export interface Draft {
  readonly name: string;
  /** Nothing chosen yet is a real state; the first card is not a default. */
  readonly family: HarnessFamily | null;
}

export const BLANK: Draft = { name: "", family: null };

export type Slot = "name" | "harness";

export interface Problem {
  readonly slot: Slot;
  /** What happened and the one thing to do about it. One line. */
  readonly message: string;
}

/**
 * The key both halves of this agent are stored under.
 *
 * Scoped to the company, the way the first-run wizard scopes the agent it
 * writes, so two companies naming an agent the same thing do not collide. It is
 * derived rather than asked because a key is machine text: the operator never
 * sees it and has no way to prefer one.
 */
export function keyOf(tenant: string, name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${tenant}.${slug}`.slice(0, 127);
}

export function problemsIn(
  draft: Draft,
  tenant: string,
  taken: readonly string[]
): readonly Problem[] {
  const problems: Problem[] = [];
  const name = draft.name.trim();
  if (name.length < NAME_LENGTH.min) {
    problems.push({ slot: "name", message: "Give this agent a name." });
  } else if (name.length > NAME_LENGTH.max) {
    problems.push({
      slot: "name",
      message: `That name is longer than ${String(NAME_LENGTH.max)} characters. Shorten it.`,
    });
  } else if (!keyPattern().test(keyOf(tenant, name))) {
    problems.push({ slot: "name", message: "Use at least three letters or digits in the name." });
  } else if (taken.some((held) => held === keyOf(tenant, name) || same(held, name))) {
    problems.push({ slot: "name", message: "This company already has an agent by that name." });
  }
  problems.push(...harnessProblems(draft));
  return problems;
}

/**
 * A harness is required and it is chosen, never typed.
 *
 * The second branch cannot be reached through the cards — an unavailable card's
 * radio is disabled, so a keyboard skips it — and it is checked anyway, because
 * the rule that an agent is never created on a harness this tower cannot start
 * belongs with the payload rather than with one control's markup.
 */
function harnessProblems(draft: Draft): readonly Problem[] {
  if (draft.family === null) {
    return [{ slot: "harness", message: "Choose the harness this agent runs on." }];
  }
  const chosen = harnessChoices().find((choice) => choice.family === draft.family);
  return chosen?.available === true
    ? []
    : [{ slot: "harness", message: "ctower cannot start an agent on that one yet." }];
}

export function problemAt(problems: readonly Problem[], slot: Slot): string | null {
  return problems.find((problem) => problem.slot === slot)?.message ?? null;
}

/**
 * What a new agent must not collide with: every key this company stores an
 * agent under, and every name it calls one by.
 *
 * Both, because they are two different collisions. Two agents under one key is
 * a record the kernel refuses; two agents under one name is a screen where the
 * operator cannot tell which is which, and the record would accept that one
 * happily. The second is the collision they will actually hit.
 */
export function recorded(document: CompanyBundleDocument): readonly string[] {
  const names = document.resources
    .filter((resource) => resource.component.kind === "persona")
    .map((resource) => resource.payload.display_name)
    .filter((name): name is string => typeof name === "string");
  return [
    ...document.resources
      .filter((resource) => resource.component.kind === "agent_profile")
      .map((resource) => resource.component.key),
    ...names,
  ];
}

/** Names collide the way a person reads them, not the way bytes compare. */
function same(held: string, name: string): boolean {
  return held.trim().toLowerCase() === name.trim().toLowerCase();
}

/**
 * The recorded bundle with one authored agent in it, and nothing else moved.
 *
 * Three components at most. The persona and the profile are always written; the
 * harness is written only when this company records none for the chosen family,
 * which is the same component the first-run wizard authors and keyed the same
 * way. That is what "created *on* a harness" means: choosing one this company
 * has never connected connects it, visibly, in the plan the operator reads
 * before anything is applied.
 */
export function documentWith(authoring: Authoring, draft: Draft): CompanyBundleDocument {
  const name = draft.name.trim();
  const family = draft.family;
  if (family === null) {
    return authoring.recorded;
  }
  const key = keyOf(authoring.tenant, name);
  const pinned = harnessRefFor(authoring.recorded, family);
  const harnessKey = `${authoring.tenant}.${family}`;
  const authored = [
    ...(pinned === null ? [harnessResource(authoring, harnessKey, family)] : []),
    resourceOf(
      {
        kind: "persona",
        schemaRef: PERSONA_SCHEMA_REF,
        payload: {
          schema: PERSONA_SCHEMA_REF,
          key,
          display_name: name,
          // The instructions this agent starts from are written on the agent's
          // own files surface, not here, so the digest is over the one thing
          // this screen was actually given. A real value over real input beats
          // a pointer at text that does not exist.
          instructions_digest: canonicalDigest({ agent: name }),
        },
        source: AUTHORED_HERE,
      },
      authoring.tenant
    ),
    resourceOf(
      {
        kind: "agent_profile",
        schemaRef: PROFILE_SCHEMA_REF,
        payload: {
          schema: PROFILE_SCHEMA_REF,
          key,
          persona_ref: `${key}@1`,
          harness_ref: pinned ?? `${harnessKey}@1`,
          skill_refs: [],
          tool_refs: [],
          execution: NOT_EXERCISED,
        },
        source: AUTHORED_HERE,
      },
      authoring.tenant
    ),
  ];
  return { ...authoring.recorded, resources: [...authoring.recorded.resources, ...authored] };
}

/**
 * The harness this company has not connected yet, written exactly as the first
 * run writes one: the adapter is the family the operator chose, and the
 * capabilities are empty because a capability is the binding's own declaration
 * and a browser claiming one would be speaking for the runner.
 */
function harnessResource(
  authoring: Authoring,
  key: string,
  family: HarnessFamily
): ReturnType<typeof resourceOf> {
  return resourceOf(
    {
      kind: "harness",
      schemaRef: "ctower.harness/v1",
      payload: {
        schema: "ctower.harness/v1",
        key,
        adapter: family,
        capabilities: [],
        execution: NOT_EXERCISED,
      },
      source: AUTHORED_HERE,
    },
    authoring.tenant
  );
}

/**
 * What an agent authored on this screen records about where it came from. An
 * authored pack names the file it was read out of; this was typed here, and the
 * provenance says so rather than borrowing another screen's path.
 */
export const AUTHORED_HERE = "ctower-web/agents";
