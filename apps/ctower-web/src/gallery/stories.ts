import type {
  CompanyBundleDocument,
  ComponentKind,
  ComponentReference,
  VersionedComponent,
} from "@ctower/client";
import type { AgentFacts } from "../agents/read";
/**
 * The staff the bench draws with.
 *
 * Fixtures, and they say so: this is the only place in `ctower-web` where a
 * person on screen is not a person in the record. They exist to put every state
 * a row can be in on one screen at one time — including the two a live company
 * rarely shows on demand, an agent whose state nothing recorded and one that
 * has never run.
 */
export const STAFF: readonly AgentFacts[] = [
  staff({
    key: "bench-ada",
    name: "Ada",
    role: "Chief of staff · CEO",
    model: "claude-fable-5",
    harness: "Claude Code",
    lastActive: "2026-08-24T09:12:00Z",
    status: "active",
  }),
  staff({
    key: "bench-luna",
    name: "Luna",
    role: "Engineer · Gate integrity",
    model: "claude-opus-5",
    harness: "Claude Code",
    lastActive: "2026-08-24T07:40:00Z",
    status: "idle",
  }),
  staff({
    key: "bench-ox",
    name: "Ox",
    role: "Reviewer · Quality",
    model: "gpt-5.2-codex",
    harness: "Codex",
    lastActive: "2026-08-23T22:05:00Z",
    status: "paused",
  }),
  staff({
    key: "bench-sol",
    name: "Sol",
    role: "Researcher · Long reads",
    model: "claude-sonnet-5",
    harness: "Hermes",
    lastActive: "2026-08-23T18:31:00Z",
    status: "error",
  }),
  staff({
    key: "bench-vela",
    name: "Vela",
    role: "Chief of staff for the whole of engineering · Second seat, weekends and nights",
    model: "claude-fable-5",
    harness: "Claude Code",
    lastActive: null,
    status: null,
  }),
];

/**
 * A payroll longer than the rail carries.
 *
 * The rail shows six names and puts the rest behind "See all agents", with the
 * count beside it. No live company on hand has eight agents, and a cap nobody
 * has seen work is a cap nobody knows is honest — so the bench has eight.
 */
export const PAYROLL: readonly AgentFacts[] = [
  "Ada",
  "Luna",
  "Ox",
  "Sol",
  "Vela",
  "Juno",
  "Rhea",
  "Kepler",
].map((name) =>
  staff({ key: `bench-${name.toLowerCase()}`, name, harness: "Claude Code", status: null })
);

/**
 * One fixture, with everything a bench story does not exercise left as the
 * record leaves it: an agent holds no skill, no tool and no seat until the
 * screens that record those exist, and a fixture that filled them would put a
 * capability on the bench that no company has.
 */
function staff(told: Partial<AgentFacts> & Pick<AgentFacts, "key" | "name">): AgentFacts {
  return {
    role: null,
    model: null,
    harness: null,
    lastActive: null,
    status: null,
    skills: [],
    tools: [],
    projects: [],
    seats: [],
    ...told,
  };
}

/**
 * A company small enough to read whole, so the instructions surface can be
 * looked at without a tower.
 *
 * It carries the one shape that surface is about: an agent profile that names a
 * persona, a skill and a tool, plus the capability the skill pins. Every
 * component is a real `VersionedComponent` and every payload satisfies its
 * authored schema, because a fixture that would be refused by the registry
 * proves nothing about a screen that authors against it.
 */
function componentOf(
  kind: ComponentKind,
  key: string,
  requires: readonly ComponentReference[] = []
): VersionedComponent {
  return {
    compatibility: { ctower: ">=0.1", requires },
    content_digest: `sha256:${key.padEnd(24, "0")}`,
    key,
    kind,
    lifecycle: "published",
    payload_ref: `object:sha256:${key}`,
    provenance: [{ digest: `sha256:${key}`, kind: "authored", source: "gallery/stories" }],
    revision: 3,
    schema: "ctower.versioned-component/v1",
    schema_ref: `ctower.${kind}/v1`,
    scope: { project: null, tenant: "acme" },
  };
}

const CAPABILITY = componentOf("capability", "acme.read-tickets");

const CAPABILITY_REF: ComponentReference = {
  content_digest: CAPABILITY.content_digest,
  key: CAPABILITY.key,
  kind: CAPABILITY.kind,
  revision: CAPABILITY.revision,
};

export const COMPANY: CompanyBundleDocument = {
  assignments: [],
  company: { display_name: "Acme", key: "acme" },
  resources: [
    {
      component: CAPABILITY,
      payload: {
        schema: "ctower.capability/v1",
        key: CAPABILITY.key,
        display_name: "Read tickets",
      },
    },
    {
      component: componentOf("persona", "acme.ada"),
      payload: {
        schema: "ctower.persona/v1",
        key: "acme.ada",
        display_name: "Ada",
        instructions_digest:
          "sha256:0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0",
      },
    },
    {
      component: componentOf("skill", "acme.triage", [CAPABILITY_REF]),
      payload: {
        schema: "ctower.skill/v1",
        key: "acme.triage",
        display_name: "Triage the inbox",
        instructions_digest:
          "sha256:1f2e3d4c5b6a79808897a6b5c4d3e2f11f2e3d4c5b6a79808897a6b5c4d3e2f1",
        capability_refs: [`${CAPABILITY.key}@${String(CAPABILITY.revision)}`],
      },
    },
    {
      component: componentOf("tool", "acme.board", [CAPABILITY_REF]),
      payload: {
        schema: "ctower.tool/v1",
        key: "acme.board",
        display_name: "The board",
        capability: CAPABILITY.key,
        authority: { grant: "none" },
      },
    },
    {
      component: componentOf("agent_profile", "acme.ada"),
      payload: {
        schema: "ctower.agent-profile/v1",
        key: "acme.ada",
        persona_ref: "acme.ada@3",
        harness_ref: "acme.claude-code@3",
        skill_refs: ["acme.triage@3"],
        tool_refs: ["acme.board@3"],
        execution: { loop_kind: "standard" },
      },
    },
  ],
  schema: "ctower.company-bundle/v1",
  secret_binding_refs: [],
};

/** The agent profile the stories open. Machine text, and it never renders. */
export const ADA = "acme.ada";
