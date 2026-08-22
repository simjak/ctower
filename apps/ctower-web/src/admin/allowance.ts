import type { ConsoleSessionAllowRequest } from "@ctower/client";

/**
 * The facts that name one exact terminal.
 *
 * An allowance is not "this crew may be watched" — it binds to one seat, one
 * piece of work, one running attempt and one live terminal at once, and the
 * tower refuses the moment any of them moves on. That is why this is twelve
 * fields and not two: the fence *is* the identity, and a screen that asked for
 * less would be offering an allowance the tower cannot grant.
 *
 * Three more fields exist in the request and are not the operator's to choose:
 * the contract fixes them to a single value each. They are stated on the screen
 * as what they are — fixed — and never as an input with one option.
 */
export type FactKey =
  | "project_key"
  | "crew_name"
  | "seat_principal_id"
  | "assignment_ticket_id"
  | "assignment_kind"
  | "assignment_interval_sequence"
  | "recorded_work_session_id"
  | "runtime_attempt_id"
  | "runner_id"
  | "runner_epoch"
  | "opaque_backend_ref"
  | "backend_incarnation";

export type Draft = Readonly<Record<FactKey, string>>;

export interface Fact {
  readonly key: FactKey;
  /** The operator's word for it, never the wire name. */
  readonly label: string;
  /** A count is a whole number the tower counts from 1; everything else is a ref. */
  readonly kind: "ref" | "count";
}

export interface FactGroup {
  readonly title: string;
  readonly facts: readonly Fact[];
}

/**
 * Grouped by where the operator gets them, not by the order the wire wants.
 * Each group is one place to look: the roster, the ticket, the runner, the box.
 */
export const FACT_GROUPS: readonly FactGroup[] = [
  {
    title: "Whose terminal",
    facts: [
      { key: "project_key", label: "Project", kind: "ref" },
      { key: "crew_name", label: "Crew", kind: "ref" },
      { key: "seat_principal_id", label: "Seat", kind: "ref" },
    ],
  },
  {
    title: "What it is working on",
    facts: [
      { key: "assignment_ticket_id", label: "Ticket", kind: "ref" },
      { key: "assignment_kind", label: "Assignment", kind: "ref" },
      { key: "assignment_interval_sequence", label: "Interval", kind: "count" },
      { key: "recorded_work_session_id", label: "Work session", kind: "ref" },
    ],
  },
  {
    title: "Which run",
    facts: [
      { key: "runtime_attempt_id", label: "Attempt", kind: "ref" },
      { key: "runner_id", label: "Runner", kind: "ref" },
      { key: "runner_epoch", label: "Epoch", kind: "count" },
    ],
  },
  {
    title: "Which terminal",
    facts: [
      { key: "opaque_backend_ref", label: "Terminal", kind: "ref" },
      { key: "backend_incarnation", label: "Incarnation", kind: "ref" },
    ],
  },
];

/** What the contract fixes, said once, as a fact rather than as a choice. */
export const FIXED: readonly string[] = ["tmux-v1", "standard loop", "restricted"];

const KEYS: readonly FactKey[] = FACT_GROUPS.flatMap((group) =>
  group.facts.map((fact) => fact.key)
);

export const EMPTY: Draft = Object.fromEntries(KEYS.map((key) => [key, ""])) as Draft;

export function withFact(draft: Draft, key: FactKey, value: string): Draft {
  return { ...draft, [key]: value };
}

/**
 * The body this draft names, or `null` while it does not name one yet.
 *
 * One function rather than a `complete()` predicate beside a builder: the two
 * would be a second place for the same rule to live, and they would drift the
 * first time a field moved. The screen arms its one primary on this returning
 * a body, and sends exactly the body it armed on.
 *
 * The shape is checked here; the *values* are not. Every pattern, length and
 * range in `ConsoleSessionAllowRequest` belongs to the authored contract, and
 * restating them here would put a second copy of the contract in the browser.
 * The tower judges, and its refusal is what renders.
 */
export function requestFrom(draft: Draft): ConsoleSessionAllowRequest | null {
  const interval = countIn(draft.assignment_interval_sequence);
  const epoch = countIn(draft.runner_epoch);
  if (interval === null || epoch === null || KEYS.some((key) => draft[key].trim() === "")) {
    return null;
  }
  return {
    adapter_key: "tmux-v1",
    loop_kind: "standard",
    sensitivity_class: "restricted",
    assignment_interval_sequence: interval,
    runner_epoch: epoch,
    project_key: draft.project_key.trim(),
    crew_name: draft.crew_name.trim(),
    seat_principal_id: draft.seat_principal_id.trim(),
    assignment_ticket_id: draft.assignment_ticket_id.trim(),
    assignment_kind: draft.assignment_kind.trim(),
    recorded_work_session_id: draft.recorded_work_session_id.trim(),
    runtime_attempt_id: draft.runtime_attempt_id.trim(),
    runner_id: draft.runner_id.trim(),
    opaque_backend_ref: draft.opaque_backend_ref.trim(),
    backend_incarnation: draft.backend_incarnation.trim(),
  };
}

function countIn(value: string): number | null {
  const parsed = Number(value.trim());
  return value.trim() !== "" && Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
}
