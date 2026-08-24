import type { Agent } from "../agents/AgentRow";

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
