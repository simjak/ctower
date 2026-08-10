import type {
  ActionBudget,
  ConsoleTyping,
  DispatchRecord,
  DispatchState,
  LiveGrant,
  Revocation,
  SessionBinding,
  TypingActor,
} from "@/surfaces/console/typing";
import { readRecordPath } from "./httpRecordAdapter";
import type { CrewLookup, Reading } from "./interface";
import { asInteger, asMember, asRecord, asString } from "./json";
import { readFailureOf } from "./outcome";

/**
 * Where one crew's typing affordance stands, or that this instance serves none.
 *
 * The three outcomes are three different things to tell an operator, and the
 * middle one is why this read does not simply go through `reading()`:
 *
 * * `present` with a session — the record answers for this console session and
 *   the affordance renders every state it reports.
 * * `present` with `null` — the API answered, and what it answered is that this
 *   browser has no console session here. That is a fact, not a failure: the
 *   console is a capability of the product rather than a field on this crew,
 *   and a surface that has none must show none. A note saying typing is coming
 *   would be the capability banner the craft rules ban, and an inert
 *   "Request type grant" button would invite a path nothing honours.
 * * `unavailable` — the API never answered at all. A console an operator cannot
 *   reach has to say so; collapsing that into the empty case would tell them
 *   there is no console when there may well be one.
 *
 * The status is what separates the last two. A refusal carries one because the
 * API spoke; an exhausted read carries none because it did not.
 *
 * Until gh#428's server lane lands, the record answers no console path, so this
 * reads `present`/`null` on the shadow instance and the crew surface is
 * unchanged. `mutate/consoleTyping.ts` is the matching write half and carries
 * the integration note.
 */

const CONSOLE_STATES: readonly DispatchState[] = [
  "unsent",
  "durability_pending",
  "accepted",
  "dispatching",
  "injected_unacknowledged",
  "acknowledged",
  "refused",
  "expired",
  "state_unknown",
];

function bindingOf(value: unknown, field: string): SessionBinding {
  const row = asRecord(value, field);
  return {
    crew: asString(row.crew, `${field}.crew`),
    incarnation: asInteger(row.incarnation, `${field}.incarnation`),
    runnerEpoch: asInteger(row.runner_epoch, `${field}.runner_epoch`),
    assignmentSequence: asInteger(row.assignment_sequence, `${field}.assignment_sequence`),
  };
}

function actorOf(value: unknown, field: string): TypingActor {
  const row = asRecord(value, field);
  return {
    role: asString(row.role, `${field}.role`),
    roleBindingRevision: asInteger(row.role_binding_revision, `${field}.role_binding_revision`),
    reauthenticatedText: asString(row.reauthenticated, `${field}.reauthenticated`),
    freshnessText: asString(row.freshness, `${field}.freshness`),
  };
}

function budgetOf(value: unknown, field: string): ActionBudget {
  const row = asRecord(value, field);
  return {
    pasteUsed: asInteger(row.paste_used, `${field}.paste_used`),
    pasteLimit: asInteger(row.paste_limit, `${field}.paste_limit`),
    submitUsed: asInteger(row.submit_used, `${field}.submit_used`),
    submitLimit: asInteger(row.submit_limit, `${field}.submit_limit`),
  };
}

function revocationOf(value: unknown, field: string): Revocation | null {
  if (value === null || value === undefined) {
    return null;
  }
  const row = asRecord(value, field);
  return {
    fact: asString(row.fact, `${field}.fact`),
    cause: asString(row.cause, `${field}.cause`),
    appendedAt: asString(row.appended_at, `${field}.appended_at`),
    streamsClosedAt: asString(row.streams_closed_at, `${field}.streams_closed_at`),
  };
}

/**
 * A grant the record already holds for this session.
 *
 * Its confirmation is read back in full, minus the exact text: those bytes are
 * in envelope-encrypted custody and never travel on an ordinary read, so a
 * grant minted in another tab shows its digest and its counts and an empty
 * command. That is the honest rendering — this browser did not write those
 * words and cannot show them.
 */
function grantOf(value: unknown, field: string): LiveGrant | null {
  if (value === null || value === undefined) {
    return null;
  }
  const row = asRecord(value, field);
  const ceremony = asRecord(row.ceremony, `${field}.ceremony`);
  return {
    grantId: asString(row.grant_id, `${field}.grant_id`),
    expiresAt: asString(row.expires_at, `${field}.expires_at`),
    grantedSeconds: asInteger(row.granted_seconds, `${field}.granted_seconds`),
    ceremony: {
      action: asMember(ceremony.action, `${field}.ceremony.action`, ["paste_text", "submit"]),
      text: "",
      requestedBytes: asInteger(ceremony.requested_bytes, `${field}.ceremony.requested_bytes`),
      plannedBytes: asInteger(ceremony.planned_bytes, `${field}.ceremony.planned_bytes`),
      digest: asString(ceremony.digest, `${field}.ceremony.digest`),
      into: bindingOf(ceremony.into, `${field}.ceremony.into`),
      reauthenticatedText: asString(ceremony.reauthenticated, `${field}.ceremony.reauthenticated`),
    },
  };
}

function dispatchOf(value: unknown, field: string): DispatchRecord | null {
  if (value === null || value === undefined) {
    return null;
  }
  const row = asRecord(value, field);
  return {
    commandId: asString(row.client_command_id, `${field}.client_command_id`),
    state: asMember(row.state, `${field}.state`, CONSOLE_STATES),
  };
}

function typingOf(value: unknown): ConsoleTyping {
  const row = asRecord(value, "console.typing");
  return {
    session: bindingOf(row.session, "console.typing.session"),
    actor: actorOf(row.actor, "console.typing.actor"),
    budget: budgetOf(row.budget, "console.typing.budget"),
    revocation: revocationOf(row.revocation, "console.typing.revocation"),
    grant: grantOf(row.grant, "console.typing.grant"),
    lastDispatch: dispatchOf(row.last_dispatch, "console.typing.last_dispatch"),
  };
}

/**
 * The crew lookup is unwrapped here rather than on the screen, for the same
 * reason `crewTerminalStream` unwraps it: a surface that branched on a read's
 * own state could turn a failed read into an empty one, and the boundary that
 * is allowed to do that is this layer.
 */
export async function readConsoleTyping(
  lookup: Reading<CrewLookup>
): Promise<Reading<ConsoleTyping | null>> {
  if (lookup.state !== "present" || lookup.value.found !== "crew") {
    return { state: "present", value: null };
  }
  const credential = process.env.CTOWER_UI_API_TOKEN;
  if (credential === undefined || credential === "") {
    // no credential was ever attached, so the API did not decline this browser
    // a console — it was never asked, and that is not an answer to render as one
    return { state: "present", value: null };
  }
  const sessionRef = lookup.value.profile.sessionName;
  try {
    const path = `/v1/console/sessions/${encodeURIComponent(sessionRef)}/typing`;
    return { state: "present", value: typingOf(await readRecordPath(path)) };
  } catch (error: unknown) {
    const failure = readFailureOf(error);
    return failure.status === null
      ? { state: "unavailable", failure }
      : { state: "present", value: null };
  }
}
