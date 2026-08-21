import type { BundleCheck } from "@ctower/client";

/**
 * The check-list shape, adopted from paperclip's `testEnvironment`.
 *
 * A row is `{code, level, message, hint}` and the status of a list is its worst
 * level. That is the whole rule, and it is worth adopting because it composes:
 * a probe that returns five cheap local checks and a registry that returns five
 * contract checks render identically, and an operator learns one thing.
 */
export type Level = "info" | "warn" | "error";

export interface Check {
  readonly code: string;
  readonly level: Level;
  readonly message: string;
  readonly hint?: string;
}

const RANK: Readonly<Record<Level, number>> = { info: 0, warn: 1, error: 2 };

/** Worst wins. An empty list has nothing wrong with it and nothing right either. */
export function worstLevel(checks: readonly Check[]): Level {
  return checks.reduce<Level>(
    (worst, check) => (RANK[check.level] > RANK[worst] ? check.level : worst),
    "info"
  );
}

/**
 * The registry's own vocabulary, said in words an operator owns.
 *
 * A code it emits and this map does not know is rendered verbatim: inventing a
 * friendly name for an unrecognised code would be this screen claiming to know
 * what the registry meant.
 */
const NAMES: Readonly<Record<string, string>> = {
  "schema.closed": "Document shape",
  "digest.canonical": "Digests match",
  "reference.exact": "References resolve",
  "compatibility.current": "Versions compatible",
  "security.secret-free": "No secrets inside",
};

/** A bundle check as a row. `passed` is information; `warning` is a warning. */
export function checkOf(check: BundleCheck): Check {
  return {
    code: check.code,
    level: check.status === "passed" ? "info" : "warn",
    message: NAMES[check.code] ?? check.code,
  };
}

export function checksOf(checks: readonly BundleCheck[]): readonly Check[] {
  return checks.map(checkOf);
}
