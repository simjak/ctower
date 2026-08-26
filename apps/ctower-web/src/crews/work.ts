import type { ProjectSessionPage } from "@ctower/client";
import type { Answer } from "../api/client";

/**
 * What one project has running, which is the one live fact this screen can
 * state without guessing.
 *
 * `listProjectSessions` answers per project, and a project key is the only key
 * a recorded session and a bundle assignment really share — so the count
 * belongs to the project, never to a row beneath it. The project header can
 * therefore say *two crews are working* while every row under it says the
 * record has not named which two, and both statements are true.
 *
 * Three shapes, and none of them collapses into another. A read still out is
 * not a project with nothing running; a read that came back refused is not a
 * project with nothing running either; and a page that did not reach the end of
 * the project's work states nothing at all, because a count over the first
 * hundred sessions of a longer history is a wrong count rather than a partial
 * one.
 */
export type Work =
  | { readonly kind: "asking" }
  | { readonly kind: "refused" }
  | {
      readonly kind: "counted";
      readonly working: number;
      readonly gated: number;
      readonly tokens: number;
    };

/** The states an open session is in while it is being worked. */
const AT_WORK: ReadonlySet<string> = new Set(["dispatched", "briefed", "working"]);

export function workOf(answer: Answer<ProjectSessionPage>): Work | null {
  if (answer.kind === "asking") {
    return { kind: "asking" };
  }
  if (answer.kind !== "answered") {
    return { kind: "refused" };
  }
  // The cursor is spent or this is not the project's work. Saying nothing is
  // the honest reading of a page that stopped early; there is no wording for
  // "at least two working" that an operator would read as anything but two.
  if (answer.value.next_cursor !== null) {
    return null;
  }
  const open = answer.value.sessions.filter((session) => session.closed_at === null);
  return {
    kind: "counted",
    working: open.filter((session) => AT_WORK.has(session.state)).length,
    gated: open.filter((session) => session.state === "gated").length,
    tokens: answer.value.sessions.reduce(
      (total, session) => total + (session.tokens?.total_tokens ?? 0),
      0
    ),
  };
}

/**
 * What a project has spent, at the precision an operator acts on.
 *
 * Compact, because the interesting comparison between two projects is an order
 * of magnitude rather than a digit, and a seven-figure number in a header is a
 * number nobody reads. The exact recorded count stays on the element's `title`.
 */
export function spend(tokens: number): string {
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(tokens);
}
