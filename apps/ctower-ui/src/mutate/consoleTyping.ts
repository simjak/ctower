import { randomUUID } from "node:crypto";
import { boundedMutation, MutationRefused, ReadRefused } from "@/read/bounded";
import { instanceIdentity } from "@/read/httpRecordAdapter";
import { asInteger, asMember, asString, PayloadRefusal } from "@/read/json";
import type {
  Ceremony,
  ConsoleAction,
  DispatchState,
  LiveGrant,
  SessionBinding,
} from "@/surfaces/console/typing";
import { REFUSAL } from "@/surfaces/console/typing";
import { commandHeaders, exactRecord, isUuid, problemSentence, uuidField } from "./command";
import type { ConsoleTypingState } from "./types";

/**
 * THE INTEGRATION POINT for gh#428's server lane.
 *
 * This is the only module in this app that names a console typing path, a
 * console request body or a console response field. The ceremony's states, copy
 * and rendering are built against the *view model* in
 * `surfaces/console/typing.ts`, not against these shapes, so when
 * `engineer-r428-server` publishes the contract in `docs/reference` exactly one
 * file changes here — this one — and no rendered state moves.
 *
 * The three operations below are the boundary
 * `docs/security/console-q3-typing-cso.md` cleared, in its own order:
 *
 * 1. **confirm** — the trusted server parses the closed action variant and
 *    derives the canonical bytes, digest, count and submit policy. It grants
 *    nothing. CT-C03 forbids trusting a client canonicalization, so this
 *    surface sends words and reads back numbers it did not compute.
 * 2. **mint** — the Access control plane, and only it, mints a
 *    `ConsoleTypeGrant` against that confirmation: one presentation, one
 *    action, at most 60 seconds, bound to the exact Actor, role binding,
 *    project, session reference, assignment interval, runner epoch, policy
 *    revision, nonce and revocation state (CT-C02).
 * 3. **dispatch** — one strict durable command under that grant. A linearizable
 *    compare-and-set immediately before the mux call admits at most one
 *    injection (CT-C04), so a duplicate press cannot inject twice and this
 *    surface never retries one on the operator's behalf.
 *
 * The browser holds nothing. The bearer is read from this server's process
 * environment, the actor and project are derived by the API from the credential
 * it validates, and the session is bound from the route rather than from a
 * payload — a browser-supplied tmux name is never authority (CT-C06).
 *
 * The exact bytes travel one way. `confirm` and `dispatch` send the operator's
 * words; nothing here reads a text field back out of a response, because
 * CT-C07 keeps exact input bytes in envelope-encrypted custody behind the
 * dedicated audited reader and out of every ordinary surface. The words on
 * screen are the ones this browser already had.
 */

const SURFACE = "ctower-ui-console-typing";
const CONFIRMATIONS = "/v1/console/typing/confirmations";
const GRANTS = "/v1/console/typing/grants";
const DISPATCHES = "/v1/console/typing/dispatches";

const ACTIONS: readonly ConsoleAction[] = ["paste_text", "submit"];
const DISPATCH_STATES: readonly DispatchState[] = [
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

/** `paste_text` carries at most 4,096 canonical bytes, so a longer draft never leaves here. */
const LONGEST_PASTE = 4096;

function credential(): string | null {
  const value = process.env.CTOWER_UI_API_TOKEN;
  return value === undefined || value === "" ? null : value;
}

function refused(message: string, text: string): ConsoleTypingState {
  return { kind: "refused", message, text };
}

/** The server's own sentence when it gave one, and this surface's own when it did not. */
function refusalFrom(error: unknown, field: string, text: string): ConsoleTypingState {
  if (error instanceof MutationRefused) {
    try {
      return refused(problemSentence(error.document, field), text);
    } catch {
      return refused(REFUSAL.unreadable, text);
    }
  }
  if (error instanceof ReadRefused) {
    return refused(REFUSAL.unreachable, text);
  }
  return refused(REFUSAL.unreachable, text);
}

async function post(path: string, commandId: string, body: unknown): Promise<unknown> {
  const bearer = credential();
  if (bearer === null) {
    throw new ReadRefused({
      reason: REFUSAL.noContract,
      failureClass: "permanent",
      attempts: 0,
      elapsedMs: 0,
      status: null,
    });
  }
  return await boundedMutation(
    `${instanceIdentity().baseUrl}${path}`,
    commandHeaders(bearer, commandId, SURFACE),
    JSON.stringify(body)
  );
}

function bindingFrom(value: unknown, field: string): SessionBinding {
  const row = exactRecord(value, field, [
    "assignment_sequence",
    "crew",
    "incarnation",
    "runner_epoch",
  ]);
  return {
    crew: asString(row.crew, `${field}.crew`),
    incarnation: asInteger(row.incarnation, `${field}.incarnation`),
    runnerEpoch: asInteger(row.runner_epoch, `${field}.runner_epoch`),
    assignmentSequence: asInteger(row.assignment_sequence, `${field}.assignment_sequence`),
  };
}

/**
 * The confirmation, read strictly and read for the numbers this surface may not
 * compute. `text` is not a field: the words came from this browser and the
 * server does not send them back.
 */
function ceremonyFrom(value: unknown, field: string, text: string): Ceremony {
  const row = exactRecord(value, field, [
    "action",
    "digest",
    "into",
    "planned_bytes",
    "reauthenticated",
    "requested_bytes",
  ]);
  const planned = asInteger(row.planned_bytes, `${field}.planned_bytes`);
  const requested = asInteger(row.requested_bytes, `${field}.requested_bytes`);
  if (planned < requested) {
    // the mux plan prepends a byte, so a plan shorter than what was asked for
    // describes some other command than the one being confirmed
    throw new PayloadRefusal(`${field}.planned_bytes`, "a plan at least as long as the request");
  }
  return {
    action: asMember(row.action, `${field}.action`, ACTIONS),
    text,
    requestedBytes: requested,
    plannedBytes: planned,
    digest: asString(row.digest, `${field}.digest`),
    into: bindingFrom(row.into, `${field}.into`),
    reauthenticatedText: asString(row.reauthenticated, `${field}.reauthenticated`),
  };
}

function grantFrom(value: unknown, field: string, ceremony: Ceremony): LiveGrant {
  const row = exactRecord(value, field, ["expires_at", "grant_id", "granted_seconds"]);
  return {
    grantId: uuidField(row.grant_id, `${field}.grant_id`),
    expiresAt: asString(row.expires_at, `${field}.expires_at`),
    grantedSeconds: asInteger(row.granted_seconds, `${field}.granted_seconds`),
    ceremony,
  };
}

/**
 * Canonicalize one draft without asking for any authority over it.
 *
 * A refusal here has injected nothing and minted nothing, because the input
 * policy runs before any accepted command, event, outbox or object mutation
 * exists (CT-C05). The operator keeps their words in every branch.
 */
export async function confirmConsoleCommand(
  sessionRef: string,
  action: ConsoleAction,
  text: string
): Promise<ConsoleTypingState> {
  const words = action === "submit" ? "" : text;
  if (action === "paste_text" && words.trim() === "") {
    return refused(REFUSAL.emptyText, text);
  }
  if (Buffer.byteLength(words, "utf8") > LONGEST_PASTE) {
    return refused(
      `This command is longer than the ${LONGEST_PASTE.toString()} bytes one paste may carry.`,
      text
    );
  }
  try {
    const answer = await post(CONFIRMATIONS, randomUUID(), {
      action,
      session_ref: sessionRef,
      text: words,
    });
    return { kind: "confirmed", ceremony: ceremonyFrom(answer, "console.confirm", words) };
  } catch (error: unknown) {
    return refusalFrom(error, "console.confirm.problem", text);
  }
}

/**
 * Ask the control plane for the 60 seconds.
 *
 * The confirmation is presented back by its digest, not by its bytes: the
 * server already holds the canonical object and re-sending the text would put
 * the exact bytes on a second wire for no gain. A digest the server did not
 * mint, or one whose stored plan has since changed, is a conflict on its side
 * and refuses there.
 */
export async function mintConsoleTypeGrant(
  sessionRef: string,
  ceremony: Ceremony
): Promise<ConsoleTypingState> {
  try {
    const answer = await post(GRANTS, randomUUID(), {
      action: ceremony.action,
      digest: ceremony.digest,
      session_ref: sessionRef,
    });
    return { kind: "granted", grant: grantFrom(answer, "console.grant", ceremony) };
  } catch (error: unknown) {
    return refusalFrom(error, "console.grant.problem", ceremony.text);
  }
}

/**
 * Present the grant once.
 *
 * `command_id` is minted here and never reused: a second press is a second
 * command, and the server's compare-and-set is what makes at most one of them
 * reach the pane. Retrying an unanswered dispatch under the same key would ask
 * the record to admit it again, and an admission whose receipt never arrived is
 * `state_unknown` — a state the operator resolves by reading the pane, not one
 * this surface resolves by pressing again.
 */
export async function dispatchConsoleInput(
  sessionRef: string,
  grant: LiveGrant,
  text: string
): Promise<ConsoleTypingState> {
  if (!isUuid(grant.grantId)) {
    return refused(REFUSAL.unreadable, text);
  }
  const commandId = randomUUID();
  try {
    const answer = await post(DISPATCHES, commandId, {
      action: grant.ceremony.action,
      client_command_id: commandId,
      grant_id: grant.grantId,
      session_ref: sessionRef,
      text: grant.ceremony.action === "submit" ? "" : grant.ceremony.text,
    });
    const row = exactRecord(answer, "console.dispatch", ["client_command_id", "state"]);
    return {
      kind: "dispatched",
      dispatch: {
        commandId: uuidField(row.client_command_id, "console.dispatch.client_command_id"),
        state: asMember(row.state, "console.dispatch.state", DISPATCH_STATES),
      },
    };
  } catch (error: unknown) {
    if (error instanceof MutationRefused) {
      return refusalFrom(error, "console.dispatch.problem", text);
    }
    // the command left this server and no answer came back: whether it was
    // admitted is exactly what nobody here knows, and saying "nothing was
    // typed" would be a claim about a pane this surface cannot see
    return {
      kind: "dispatched",
      dispatch: { commandId, state: "state_unknown" },
    };
  }
}
