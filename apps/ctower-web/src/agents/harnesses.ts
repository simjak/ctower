import { Braces, Feather, Pi, SquareTerminal } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * The harnesses an agent can be created on, in the operator's words.
 *
 * A harness is chosen from a card, never typed. That is the whole point of the
 * picker: the operator picks the thing they know the name of, and everything
 * the record needs underneath — which component this is, at which revision — is
 * derived from the choice by the screen that wires this, not asked for here.
 *
 * So this file holds exactly the facts a person needs to choose between them: a
 * name they already say out loud, one line of what it is, and whether ctower can
 * actually run an agent on it today. `family` is an internal name and renders
 * nowhere.
 *
 * `available` is not decoration. `apps/ctower-runner` carries a binding for
 * Claude Code, Codex and Hermes and none for Pi, so Pi is offered as an unbuilt
 * card rather than left out: a harness the operator asked for and ctower cannot
 * run yet is a real state, and `DESIGN.md` draws those honestly instead of
 * hiding them.
 */
export type HarnessFamily = "claude-code" | "codex" | "hermes" | "pi";

export interface HarnessChoice {
  /** Internal; never rendered. */
  readonly family: HarnessFamily;
  readonly name: string;
  /** One line. What it is, not how it is wired. */
  readonly blurb: string;
  readonly icon: LucideIcon;
  /** The one this console is proven against. At most a few, or the badge says nothing. */
  readonly recommended: boolean;
  /** Whether an agent can be created on it today. */
  readonly available: boolean;
}

const CATALOG: readonly HarnessChoice[] = [
  {
    family: "claude-code",
    name: "Claude Code",
    blurb: "Anthropic's coding agent, at home in a terminal.",
    icon: SquareTerminal,
    recommended: true,
    available: true,
  },
  {
    family: "codex",
    name: "Codex",
    blurb: "OpenAI's coding agent, for work that runs long.",
    icon: Braces,
    recommended: false,
    available: true,
  },
  {
    family: "hermes",
    name: "Hermes",
    blurb: "The in-house agent, on machines you already own.",
    icon: Feather,
    recommended: false,
    available: true,
  },
  {
    family: "pi",
    name: "Pi",
    blurb: "ctower has no way to start it yet.",
    icon: Pi,
    recommended: false,
    available: false,
  },
];

/**
 * The adapters this console can put a name to, which is not the same list.
 *
 * A recorded harness carries an `adapter` and no display name — the component
 * schema is closed and has no field for one — so naming one on screen means
 * knowing what its adapter is. Two of these are not cards: `ctowerctl`'s
 * generated client is how the commander seat reaches the control plane, and it
 * is a harness a company really runs on without being one an operator picks
 * when making an agent.
 *
 * An adapter that is not here gets **no** name rather than its own machine
 * text dressed up as one. A blank is a fact an operator can ask about; a
 * lower-cased key with the dots taken out is the console pretending.
 */
const NAMED_ADAPTERS: ReadonlyMap<string, string> = new Map([
  ["claude-code", "Claude Code"],
  ["claude_code", "Claude Code"],
  ["codex", "Codex"],
  ["hermes", "Hermes"],
  ["ctowerctl.generated_client", "ctower CLI"],
]);

/** What a recorded harness is called, when this console can say honestly. */
export function harnessNamed(adapter: string | null): string | null {
  return adapter === null ? null : (NAMED_ADAPTERS.get(adapter) ?? null);
}

/** Every harness this console knows how to offer, in the order it offers them. */
export function harnessChoices(): readonly HarnessChoice[] {
  return CATALOG;
}
