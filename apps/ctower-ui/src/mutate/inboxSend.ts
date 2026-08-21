import { randomUUID } from "node:crypto";
import { boundedMutation, MutationRefused, ReadRefused } from "@/read/bounded";
import { defaultProjectKey } from "@/read/projects";
import { instanceIdentity, loadInboxCorrespondent } from "@/read/httpRecordAdapter";
import { asInteger, asMember, asString, PayloadRefusal } from "@/read/json";
import { commandHeaders, exactRecord, isUuid, problemSentence, uuidField } from "./command";
import type { InboxSendState } from "./types";

const DURABILITY = ["accepted", "durability_pending"] as const;
const SURFACE = "ctower-ui-send";
/** `InboxSendRequest.text`'s authored ceiling; the server refuses past it. */
const LONGEST_MESSAGE = 65536;

// D9's error budget is fact + next action and nothing else, counted at 60
// characters: the sentences these replace explained the durability model on
// screen, which is this document's job rather than the box's.
const UNCONFIRMED = "Not sent yet. Press send again.";
const LOST_REPLAY = "Lost track of this retry. Reload and send again.";

/** One attempt at one message: what was sent, what was typed, and under which identity. */
interface Attempt {
  readonly threadId: string;
  /** The message as it went on the wire. */
  readonly message: string;
  /** The words as the operator typed them. */
  readonly text: string;
  readonly commandId: string;
}

/**
 * The command's own answer, read strictly, and read for which state it names.
 *
 * `durability_state` is the whole difference between a recorded message and one
 * the record has not promised to keep: a `202` answer carries the same message
 * identity, position and timestamp the accepted answer does. So the accepted
 * fields are read only on the accepted branch, and the non-accepted one returns
 * the sender's words and the identity a retry sends again — nothing that could
 * be drawn as a message.
 *
 * On the accepted branch `text` is the text this command sent. The result
 * carries every other field the record assigned — identity, position, timestamp
 * — and does not echo the body back, so the one value not read from the
 * response is the one the caller already holds.
 */
function answerFrom(value: unknown, attempt: Attempt): InboxSendState {
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
  const row = exactRecord(value, "inbox.send", fields);
  uuidField(row.command_id, "inbox.send.command_id");
  const durability = asMember(row.durability_state, "inbox.send.durability_state", DURABILITY);
  asInteger(row.thread_version, "inbox.send.thread_version");
  const severity = asMember(row.severity, "inbox.send.severity", ["P0", "P1", "info"] as const);
  if (uuidField(row.thread_id, "inbox.send.thread_id") !== attempt.threadId) {
    throw new PayloadRefusal("inbox.send.thread_id", "the thread this message was sent on");
  }
  if (durability !== "accepted") {
    return {
      kind: "pending",
      message: UNCONFIRMED,
      text: attempt.text,
      commandId: attempt.commandId,
    };
  }
  return {
    kind: "sent",
    message: {
      messageId: uuidField(row.message_id, "inbox.send.message_id"),
      position: asInteger(row.position, "inbox.send.position"),
      from: asString(row.from, "inbox.send.from"),
      to: asString(row.to, "inbox.send.to"),
      text: attempt.message,
      sentAt: asString(row.sent_at, "inbox.send.sent_at"),
      severity,
    },
  };
}

/** Every refusal hands the typed text back: nobody retypes what they just wrote. */
function refused(message: string, text: string): InboxSendState {
  return { kind: "refused", message, text };
}

/**
 * Send one message on an existing thread through the authored send command.
 *
 * The browser supplies the message text and the answer it last received. The
 * thread comes from the route this action was bound to, the recipient is read
 * back from the server's own recipient-scoped projection at submit time, and
 * the sender is never sent at all — the API derives it from the bearer this
 * server holds. A recipient a browser could edit would be a claimed identity,
 * so there is no form field for one.
 *
 * `previous` exists for one value: the identity of a send the record answered
 * without accepting. Retrying that message under a new identity would ask the
 * record to keep two copies of it, so the retry sends the same one and the
 * record replays its own command instead.
 */
export async function sendInboxMessage(
  threadId: string,
  text: string,
  previous: InboxSendState
): Promise<InboxSendState> {
  if (!isUuid(threadId)) {
    return refused("Open a thread before sending a message.", text);
  }
  const message = text.trim();
  if (message === "") {
    return refused("Write a message before sending.", text);
  }
  if (message.length > LONGEST_MESSAGE) {
    return refused(
      `This message is too long. The limit is ${LONGEST_MESSAGE.toString()} characters.`,
      text
    );
  }
  const credential = process.env.CTOWER_UI_API_TOKEN;
  if (credential === undefined || credential === "") {
    return refused("This server holds no API credential.", text);
  }
  // The browser's copy of the last answer is an outside payload, so the one
  // value read out of it is read strictly. Only an unconfirmed send carries an
  // identity to reuse, and only for the same message: a different message is a
  // different command, and one key for two different requests is a conflict
  // rather than a retry.
  const replay = previous.kind === "pending" && previous.text.trim() === message ? previous : null;
  if (replay !== null && !isUuid(replay.commandId)) {
    return refused(LOST_REPLAY, text);
  }
  let recipient: string;
  try {
    recipient = (await loadInboxCorrespondent(threadId)).recipient;
  } catch {
    return refused("The recipient could not be read. Nothing was sent.", text);
  }
  const commandId = replay === null ? randomUUID() : replay.commandId;
  try {
    const result = await boundedMutation(
      `${instanceIdentity().baseUrl}/v1/inbox/messages`,
      commandHeaders(credential, commandId, SURFACE),
      JSON.stringify({
        project_key: defaultProjectKey(),
        severity: "info",
        text: message,
        thread_id: threadId,
        to: recipient,
      })
    );
    return answerFrom(result, { threadId, message, text, commandId });
  } catch (error: unknown) {
    if (error instanceof MutationRefused) {
      try {
        return refused(problemSentence(error.document, "inbox.send.problem"), text);
      } catch {
        return refused("The server refused the message without a usable explanation.", text);
      }
    }
    if (error instanceof ReadRefused) {
      return refused("The server could not accept the message. Try again.", text);
    }
    return refused("The message could not reach the server. Try again.", text);
  }
}
