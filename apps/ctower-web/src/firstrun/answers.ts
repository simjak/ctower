import type { CompanyBundleDocument } from "@ctower/client";
import { canonicalDigest } from "../mint/digest";
import { resourceOf } from "../mint/component";

/** The adapters this wizard can stand a team up on. */
export interface Adapter {
  readonly key: string;
  readonly label: string;
  readonly blurb: string;
  readonly recommended: boolean;
}

/**
 * The three adapters the runner actually has a binding for. `hermes`,
 * `claude-code` and `codex` are the three the conformance suite covers; a card
 * for anything else would be offering a harness with nothing behind it, which
 * is how a stub becomes an adapter by accident.
 */
export const ADAPTERS: readonly Adapter[] = [
  {
    key: "claude-code",
    label: "Claude Code",
    blurb: "Claude Code CLI harness",
    recommended: true,
  },
  { key: "codex", label: "Codex", blurb: "Codex CLI harness", recommended: true },
  { key: "hermes", label: "Hermes", blurb: "Hermes profile harness", recommended: false },
];

/** Everything the five steps collect, and nothing else. */
export interface Answers {
  readonly name: string;
  readonly key: string;
  readonly adapter: string;
  readonly agentName: string;
  /** Empty when the operator skipped the mission; that is a real state. */
  readonly mission: string;
  readonly criterion: string;
}

export const BLANK: Answers = {
  name: "",
  key: "",
  adapter: "claude-code",
  agentName: "Commander",
  mission: "",
  criterion: "",
};

/** A suggested key, until the operator types their own. */
export function suggestKey(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

function slug(value: string, fallback: string): string {
  const derived = suggestKey(value);
  return derived.length >= 3 ? derived : fallback;
}

/**
 * The five answers as the authored contract's own document.
 *
 * Four components, each real: the harness the team runs on, the persona the
 * agent speaks as, the profile that pairs them, and a goal when a mission was
 * given. The assignment binds the profile to the seat. Every digest is computed
 * here the way the kernel computes it, and the registry recomputes every one of
 * them — a wrong byte is a refused bundle, not a quiet acceptance.
 */
export function bundleOf(answers: Answers): CompanyBundleDocument {
  const tenant = answers.key;
  const agentKey = `${tenant}.${slug(answers.agentName, "lead")}`;

  const harness = {
    schema: "ctower.harness/v1",
    key: `${tenant}.${answers.adapter}`,
    adapter: answers.adapter,
    capabilities: [],
    execution: "not_exercised",
  } as const;

  const persona = {
    schema: "ctower.persona/v1",
    key: agentKey,
    display_name: answers.agentName,
    // The instructions this agent starts from are the mission the operator
    // wrote, so the digest is of that text and of nothing invented. With no
    // mission it is the digest of the agent's own name — still a real value
    // over real input, never a pointer at something that does not exist.
    instructions_digest: canonicalDigest(
      answers.mission === "" ? { agent: answers.agentName } : { mission: answers.mission }
    ),
  } as const;

  const profile = {
    schema: "ctower.agent-profile/v1",
    key: agentKey,
    persona_ref: `${agentKey}@1`,
    harness_ref: `${harness.key}@1`,
    skill_refs: [],
    tool_refs: [],
    execution: "not_exercised",
  } as const;

  const resources = [
    resourceOf({ kind: "harness", schemaRef: "ctower.harness/v1", payload: harness }, tenant),
    resourceOf({ kind: "persona", schemaRef: "ctower.persona/v1", payload: persona }, tenant),
    resourceOf(
      { kind: "agent_profile", schemaRef: "ctower.agent-profile/v1", payload: profile },
      tenant
    ),
  ];

  if (answers.mission !== "") {
    const goal = {
      schema: "ctower.goal/v1",
      key: `${tenant}.mission`,
      display_name: "Mission",
      outcome: answers.mission,
      success_criteria: [answers.criterion === "" ? answers.mission : answers.criterion],
    } as const;
    resources.push(
      resourceOf({ kind: "goal", schemaRef: "ctower.goal/v1", payload: goal }, tenant)
    );
  }

  const bound = resources[2];
  if (bound === undefined) {
    throw new TypeError("the agent profile is missing from the minted bundle");
  }

  return {
    schema: "ctower.company-bundle/v1",
    company: { key: tenant, display_name: answers.name },
    resources,
    assignments: [
      {
        subject: `${tenant}:${slug(answers.agentName, "lead")}`,
        slot: "agent_profile",
        component: {
          kind: "agent_profile",
          key: bound.component.key,
          revision: bound.component.revision,
          content_digest: bound.component.content_digest,
        },
      },
    ],
    secret_binding_refs: [],
  };
}
