import { randomUUID } from "node:crypto";
import { boundedMutation, MutationRefused, ReadRefused } from "@/read/bounded";
import { defaultProjectKey } from "@/read/projects";
import { instanceIdentity, loadInboxCorrespondents } from "@/read/httpRecordAdapter";
import { asInteger, asMember, asString, PayloadRefusal } from "@/read/json";
import { commandHeaders, exactRecord, isUuid, problemSentence, uuidField } from "./command";
import type { InboxComposeState } from "./types";

const DURABILITY = ["accepted", "durability_pending"] as const;
const SURFACE = "ctower-ui-compose";
/** `InboxNotificationRequest.text`'s authored ceiling; the server refuses past it. */
const LONGEST_MESSAGE = 65536;

// The same D9 error budget the send path is held to: fact, next action, and no
// sentence about why durability works the way it does.
const UNCONFIRMED = "Not started yet. Press send again.";
const LOST_REPLAY = "Lost track of this retry. Reload and send again.";
const UNLISTED = "The record does not list that seat. Pick one listed.";

/** One attempt at opening one thread: to whom, with what, under which identity. */
interface Attempt {
  readonly to: string;
  /** The message as it went on the wire. */
  readonly message: string;
  /** The words as the operator typed them. */
  readonly text: string;
  readonly commandId: string;
}

/**
 * The command's own answer, read strictly, and read for which state it names.
 *
 * The two states share one envelope: a `202` answer carries the same thread
 * identity, message identity, position and timestamp the accepted answer does,
 * and means the opposite thing. So the accepted fields are read only on the
 * accepted branch, and the non-accepted one returns the operator's words and
 * the identity a retry sends again — nothing that could be drawn as a started
 * conversation.
 *
 * The thread identity is read on both branches for one reason: it is the whole
 * answer to *where the message went*. It is the record's, not this surface's —
 * the server derives it from the seat pair, which is why composing twice to one
 * seat continues one thread instead of starting two.
 */
function answerFrom(value: unknown, attempt: Attempt): InboxComposeState {
  const fields = [
    "command_id",
    "durability_state",
    "event_ids",
    "from",
    "message_id",
    "position",
    "sent_at",
    "severity",
    "thread_id",
    "thread_version",
    "to",
  ] as const;
  const row = exactRecord(value, "inbox.compose", fields);
  uuidField(row.command_id, "inbox.compose.command_id");
  const durability = asMember(row.durability_state, "inbox.compose.durability_state", DURABILITY);
  asInteger(row.thread_version, "inbox.compose.thread_version");
  const severity = asMember(row.severity, "inbox.compose.severity", ["P0", "P1", "info"] as const);
  const threadId = uuidField(row.thread_id, "inbox.compose.thread_id");
  if (asString(row.to, "inbox.compose.to") !== attempt.to) {
    throw new PayloadRefusal("inbox.compose.to", "the seat this message was addressed to");
  }
  if (durability !== "accepted") {
    return {
      kind: "pending",
      message: UNCONFIRMED,
      text: attempt.text,
      to: attempt.to,
      commandId: attempt.commandId,
    };
  }
  return {
    kind: "started",
    threadId,
    message: {
      messageId: uuidField(row.message_id, "inbox.compose.message_id"),
      position: asInteger(row.position, "inbox.compose.position"),
      from: asString(row.from, "inbox.compose.from"),
      to: attempt.to,
      text: attempt.message,
      sentAt: asString(row.sent_at, "inbox.compose.sent_at"),
      severity,
    },
  };
}

/** Every refusal hands the typed text and the chosen seat back. */
function refused(message: string, text: string, to: string): InboxComposeState {
  return { kind: "refused", message, text, to };
}

/**
 * Open or continue the thread between this principal and one registered seat.
 *
 * The browser submits two values: the message, and which of the seats the
 * server itself listed it is for. Neither is an identity claim. The sender is
 * never sent at all — the API derives it from the bearer this server holds —
 * and the recipient is checked back against that same server-listed closed
 * world before any command is made, so a seat a browser invented is refused
 * here, and a seat the record has since dropped is refused by the record.
 *
 * The thread is not chosen at all. The server derives one thread per unordered
 * seat pair, so a second compose to the same seat continues the conversation
 * the first one opened — including the one the notification mirror opened.
 *
 * `previous` exists for one value: the identity of a send the record answered
 * without accepting. Retrying that message under a new identity would ask the
 * record to keep two copies of it, so the retry sends the same one and the
 * record replays its own command instead.
 */
export async function composeInboxThread(
  to: string,
  text: string,
  previous: InboxComposeState
): Promise<InboxComposeState> {
  const message = text.trim();
  if (to === "") {
    return refused("Pick the seat this message is for.", text, to);
  }
  if (message === "") {
    return refused("Write a message before sending.", text, to);
  }
  if (message.length > LONGEST_MESSAGE) {
    return refused(
      `This message is too long. The limit is ${LONGEST_MESSAGE.toString()} characters.`,
      text,
      to
    );
  }
  const credential = process.env.CTOWER_UI_API_TOKEN;
  if (credential === undefined || credential === "") {
    return refused("This server holds no API credential.", text, to);
  }
  // The browser's copy of the last answer is an outside payload, so the one
  // value read out of it is read strictly. Only an unconfirmed send carries an
  // identity to reuse, and only for the same message to the same seat: anything
  // else is a different request, and one key for two different requests is a
  // conflict rather than a retry.
  const replay =
    previous.kind === "pending" && previous.text.trim() === message && previous.to === to
      ? previous
      : null;
  if (replay !== null && !isUuid(replay.commandId)) {
    return refused(LOST_REPLAY, text, to);
  }
  let listed: readonly string[];
  try {
    listed = (await loadInboxCorrespondents()).choices.map((choice) => choice.seatKey);
  } catch {
    return refused("The seat list could not be read. Nothing was sent.", text, to);
  }
  if (!listed.includes(to)) {
    return refused(UNLISTED, text, to);
  }
  const commandId = replay === null ? randomUUID() : replay.commandId;
  try {
    const result = await boundedMutation(
      `${instanceIdentity().baseUrl}/v1/inbox/notifications`,
      commandHeaders(credential, commandId, SURFACE),
      JSON.stringify({ project_key: defaultProjectKey(), severity: "info", text: message, to })
    );
    return answerFrom(result, { to, message, text, commandId });
  } catch (error: unknown) {
    if (error instanceof MutationRefused) {
      try {
        return refused(problemSentence(error.document, "inbox.compose.problem"), text, to);
      } catch {
        return refused("The server refused the message without a usable explanation.", text, to);
      }
    }
    if (error instanceof ReadRefused) {
      return refused("The server could not accept the message. Try again.", text, to);
    }
    return refused("The message could not reach the server. Try again.", text, to);
  }
}
