import type { RequestList, RequestRow } from "@ctower/client";
import type { MarkName } from "../ui/marks";

/**
 * What a Request row says, in the operator's vocabulary.
 *
 * A Request carries two independent facts and this module keeps them apart:
 * `state` is where the work is, `triage` is what was decided about the ask.
 * `TRIAGED · DUPLICATE` and `TRIAGED · ACCEPTED` are opposite instructions to a
 * reader, so a screen that renders only one of them is lying by omission.
 *
 * Both tables are keyed over the full union the contract declares, so a value
 * the record is allowed to hold can never arrive and render as nothing.
 */
export type Tone = "neutral" | "amber" | "ok" | "danger";

/**
 * Where the work is, in the six glyphs `ctowerctl` prints. The mapping is the
 * mark vocabulary's own meaning rather than a second scale invented here:
 * blocked work is parked, not dead.
 */
const STATE_MARK: Readonly<Record<RequestRow["state"], MarkName>> = {
  NEW: "idle",
  TRIAGED: "idle",
  WIP: "working",
  BLOCKED: "parked",
  DONE: "done",
};

/**
 * What was decided. Two tones are spent and no more: `UNTRIAGED` is the only
 * value asking the reader for a decision, and `REJECTED` is the only refusal —
 * which is the whole of what danger means in this system.
 */
const TRIAGE_TONE: Readonly<Record<RequestRow["triage"], Tone>> = {
  UNTRIAGED: "amber",
  ACCEPTED: "neutral",
  DUPLICATE: "neutral",
  REJECTED: "danger",
};

export function stateMark(state: RequestRow["state"]): MarkName {
  return STATE_MARK[state];
}

export function triageTone(triage: RequestRow["triage"]): Tone {
  return TRIAGE_TONE[triage];
}

/** A P0 is the only priority that earns the accent; the rest are values. */
export function priorityTone(priority: RequestRow["priority"]): Tone {
  return priority === "P0" ? "amber" : "neutral";
}

/**
 * How long the ask has been waiting, at the coarseness a person reads.
 *
 * One unit, never two: an operator scanning a column wants "3d" against "4h",
 * and a second unit buys precision nobody spends. The exact filing time is in
 * the detail, where precision is what the reader came for.
 */
export function age(seconds: number): string {
  if (seconds < 60) {
    return `${String(seconds)}s`;
  }
  if (seconds < 3600) {
    return `${String(Math.floor(seconds / 60))}m`;
  }
  if (seconds < 172800) {
    return `${String(Math.floor(seconds / 3600))}h`;
  }
  return `${String(Math.floor(seconds / 86400))}d`;
}

/** The record's own timestamp, trimmed to the minute and kept in UTC. */
export function moment(iso: string): string {
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}Z`;
}

/** A digest at the length a person actually compares one; the full value hovers. */
export function shortDigest(digest: string): string {
  return `${digest.slice(0, 14)}…`;
}

/**
 * How much of the portfolio this answer covers.
 *
 * `unanswered_projects` is the epistemic half of the read and is never inferred
 * from a row count: a project that did not answer is not a project with no
 * requests, and the two must never render alike.
 */
export function coverage(list: RequestList): string {
  const asked = list.requested_project_count;
  const noun = asked === 1 ? "project" : "projects";
  return `${String(list.answered_project_count)} of ${String(asked)} ${noun} answered`;
}
