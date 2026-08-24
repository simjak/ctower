import type { Agent } from "../agents/AgentRow";
import type { ListedAgent } from "../agents/read";

/**
 * The staff the bench draws with.
 *
 * Fixtures, and they say so: this is the only place in `ctower-web` where a
 * person on screen is not a person in the record. They exist to put every state
 * a row can be in on one screen at one time — including the two a live company
 * rarely shows on demand, an agent whose state nothing recorded and one that
 * has never run.
 */
export const STAFF: readonly Agent[] = [
  {
    name: "Ada",
    role: "Chief of staff · CEO",
    model: "claude-fable-5",
    harness: "Claude Code",
    lastActive: "2026-08-24T09:12:00Z",
    status: "active",
  },
  {
    name: "Luna",
    role: "Engineer · Gate integrity",
    model: "claude-opus-5",
    harness: "Claude Code",
    lastActive: "2026-08-24T07:40:00Z",
    status: "idle",
  },
  {
    name: "Ox",
    role: "Reviewer · Quality",
    model: "gpt-5.2-codex",
    harness: "Codex",
    lastActive: "2026-08-23T22:05:00Z",
    status: "paused",
  },
  {
    name: "Sol",
    role: "Researcher · Long reads",
    model: "claude-sonnet-5",
    harness: "Hermes",
    lastActive: "2026-08-23T18:31:00Z",
    status: "error",
  },
  {
    name: "Vela",
    role: "Chief of staff for the whole of engineering · Second seat, weekends and nights",
    model: "claude-fable-5",
    harness: "Claude Code",
    lastActive: null,
    status: null,
  },
];

/**
 * A payroll longer than the rail carries.
 *
 * The rail shows six names and puts the rest behind "See all agents", with the
 * count beside it. No live company on hand has eight agents, and a cap nobody
 * has seen work is a cap nobody knows is honest — so the bench has eight.
 */
export const PAYROLL: readonly ListedAgent[] = [
  "Ada",
  "Luna",
  "Ox",
  "Sol",
  "Vela",
  "Juno",
  "Rhea",
  "Kepler",
].map((name) => ({
  key: `bench-${name.toLowerCase()}`,
  agent: {
    name,
    role: null,
    model: null,
    harness: "Claude Code",
    lastActive: null,
    status: null,
  },
}));
