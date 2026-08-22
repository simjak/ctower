import type { TicketSession } from "@ctower/client";
import type { MarkName } from "../ui/marks";

/**
 * What one recorded session is allowed to claim about itself.
 *
 * The mark vocabulary is the CLI's six glyphs and it is closed, so a recorded
 * state only draws one when a glyph actually means it. `dispatched`, `briefed`
 * and `working` are three stages of one session that is in flight, so they
 * share the in-flight glyph and each carries its own exact word beside it; the
 * word is what distinguishes them, never the mark.
 *
 * A session whose record closed without an outcome draws no mark at all. That
 * is the contract disagreeing with itself, not a state, and borrowing a glyph
 * for it would render a defect as a result.
 */
export interface Liveness {
  readonly mark: MarkName | null;
  /** One word: the record's own, wherever the record has one. */
  readonly word: string;
}

const OPEN: Readonly<Record<TicketSession["state"], Liveness>> = {
  dispatched: { mark: "working", word: "dispatched" },
  briefed: { mark: "working", word: "briefed" },
  working: { mark: "working", word: "working" },
  gated: { mark: "parked", word: "gated" },
};

const CLOSED: Readonly<Record<NonNullable<TicketSession["outcome"]>, Liveness>> = {
  delivered: { mark: "done", word: "delivered" },
  blocked: { mark: "parked", word: "blocked" },
  abandoned: { mark: "dead", word: "abandoned" },
  failed: { mark: "dead", word: "failed" },
};

const UNKNOWN: Liveness = { mark: null, word: "unknown" };

export function livenessOf(session: TicketSession): Liveness {
  if (session.closed_at === null) {
    return OPEN[session.state];
  }
  return session.outcome === null ? UNKNOWN : CLOSED[session.outcome];
}
