import type { MarkName } from "../../ui/marks";

/**
 * What a crew is on this screen, and what the record can actually say about one.
 *
 * A crew is not a component. It is a subject the company binds an agent profile
 * to — the bundle's own `agent_profile` assignment — so a crew's NAME and the
 * HARNESS it is set up on are read off the active bundle and are real.
 *
 * Everything a fleet dashboard wants beside that — is it working, on which
 * model, how many tokens, when it last moved — lives on a recorded session, and
 * a session names its crew with a string the caller authored. `SPEC.md` is
 * explicit that a seat key is never inferred from a subject or display text, so
 * this console cannot say the session called `qa-crew-4` is the crew the bundle
 * calls `QA`. Those columns are therefore `null` on every row a live tower would
 * hand this screen today, and a row draws nothing where it has nothing.
 *
 * The bench draws both: the roster as the record answers it now, and the same
 * rows once a session can name the crew it ran as. The gap between the two
 * pictures is the ruling this design is asking for, not something to paper over.
 */
export interface Crew {
  /** The persona's own `display_name`, or the seat when no persona names one. */
  readonly name: string;
  /** What this crew does, when the company recorded a line for it. */
  readonly role: string | null;
  /** A product name a person says out loud: "Claude Code". Never an adapter. */
  readonly harness: string | null;
  /** The model a recorded run served. A crew's profile records none. */
  readonly model: string | null;
  /** The last thing the record saw this crew do. */
  readonly standing: Standing;
  /** What that run spent, when a run can be attributed to this crew. */
  readonly tokens: number | null;
  readonly lastActive: string | null;
}

/**
 * The state of a run, in the operator's words.
 *
 * Both halves are closed sets of the authored contract — `SessionState` while a
 * run is open, `SessionOutcome` once it closed — so every word here is one the
 * record really distinguishes, and every mark is one `ctowerctl` already prints.
 * `unseen` is the state of a crew no run has been attributed to. It draws no
 * mark, because unknown is first-class and borrowing a neighbour's glyph is how
 * a read that never answered gets rendered as a state that did.
 */
export type Standing =
  | "dispatched"
  | "briefed"
  | "working"
  | "gated"
  | "delivered"
  | "blocked"
  | "abandoned"
  | "failed"
  | "ended"
  | "unseen";

export interface Reading {
  readonly mark: MarkName | null;
  /** Two words is the budget, and it is the operator's word, not the wire's. */
  readonly word: string;
  readonly tone: "neutral" | "amber" | "ok" | "danger";
}

const READING: Readonly<Record<Standing, Reading>> = {
  dispatched: { mark: "idle", word: "sent out", tone: "neutral" },
  briefed: { mark: "idle", word: "briefed", tone: "neutral" },
  working: { mark: "working", word: "working", tone: "amber" },
  // "at a gate" is the operator's own phrase and it is three words, which the
  // copy budget does not have. The mark already says parked; the word says what
  // the crew is doing about it.
  gated: { mark: "parked", word: "waiting", tone: "neutral" },
  delivered: { mark: "done", word: "delivered", tone: "ok" },
  blocked: { mark: "warn", word: "stuck", tone: "amber" },
  abandoned: { mark: "parked", word: "dropped", tone: "neutral" },
  failed: { mark: "dead", word: "failed", tone: "danger" },
  ended: { mark: null, word: "ended", tone: "neutral" },
  unseen: { mark: null, word: "not seen", tone: "neutral" },
};

export function readingOf(standing: Standing): Reading {
  return READING[standing];
}

/** Whether a crew is one the record currently has at work. */
export function atWork(standing: Standing): boolean {
  return standing === "working" || standing === "briefed" || standing === "dispatched";
}

/**
 * What a run spent, at the precision an operator acts on.
 *
 * Compact, because the interesting comparison between two crews is an order of
 * magnitude rather than a digit, and a six-figure number in a row is a number
 * nobody reads. The exact recorded count stays on the element's `title`.
 */
export function spend(tokens: number): string {
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(tokens);
}
