import type { MarkName } from "../ui/marks";

/**
 * What an agent is doing, and the two things a row is allowed to draw for it.
 *
 * The mark is the CLI's own glyph — `DESIGN.md` makes that vocabulary shared,
 * so the dot beside a name here is the same character `ctowerctl` prints for
 * the same state, and it changes in both places or neither.
 *
 * An agent with no recorded state draws NO mark and says `unknown` in words.
 * That is the same law the crews page's sessions follow: unknown is first-class,
 * and borrowing the neighbouring glyph is how a read that never answered gets
 * rendered as a state that did.
 */
export type AgentStatus = "active" | "idle" | "paused" | "error";

export interface Standing {
  readonly mark: MarkName | null;
  /** One word, and it is the operator's, not the record's shape. */
  readonly word: string;
  readonly tone: "neutral" | "amber" | "danger";
}

const STANDING: Readonly<Record<AgentStatus, Standing>> = {
  active: { mark: "working", word: "active", tone: "amber" },
  idle: { mark: "idle", word: "idle", tone: "neutral" },
  paused: { mark: "parked", word: "paused", tone: "neutral" },
  error: { mark: "dead", word: "error", tone: "danger" },
};

const UNKNOWN: Standing = { mark: null, word: "unknown", tone: "neutral" };

export function standingOf(status: AgentStatus | null): Standing {
  return status === null ? UNKNOWN : STANDING[status];
}
