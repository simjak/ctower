import { randomUUID } from "node:crypto";
import { boundedMutation, MutationRefused, ReadRefused } from "@/read/bounded";
import { instanceIdentity, loadInboxCorrespondent } from "@/read/httpRecordAdapter";
import { asInteger, asMember, asString, PayloadRefusal } from "@/read/json";
import { commandHeaders, exactRecord, isUuid, problemSentence, uuidField } from "./command";
import type { InboxSendState } from "./types";

const DURABILITY = ["accepted", "durability_pending"] as const;
const SURFACE = "ctower-ui-send";
/** `InboxSendRequest.text`'s authored ceiling; the server refuses past it. */
const LONGEST_MESSAGE = 65536;

/**
 * The accepted message, read strictly out of the command's own answer.
 *
 * `text` is the text this command sent. The result carries every other field
 * the record assigned — identity, position, timestamp — and does not echo the
 * body back, so the one value not read from the response is the one the caller
 * already holds.
 */
function sentFrom(
  value: unknown,
  expectedThreadId: string,
  text: string
): Extract<InboxSendState, { readonly kind: "sent" }> {
  const fields = [
    "command_id",
    "durability_state",
    "event_ids",
    "from",
    "message_id",
    "position",
    "sent_at",
    "thread_id",
    "thread_version",
    "to",
  ] as const;
  const row = exactRecord(value, "inbox.send", fields);
  uuidField(row.command_id, "inbox.send.command_id");
  asMember(row.durability_state, "inbox.send.durability_state", DURABILITY);
  asInteger(row.thread_version, "inbox.send.thread_version");
  if (uuidField(row.thread_id, "inbox.send.thread_id") !== expectedThreadId) {
    throw new PayloadRefusal("inbox.send.thread_id", "the thread this message was sent on");
  }
  return {
    kind: "sent",
    message: {
      messageId: uuidField(row.message_id, "inbox.send.message_id"),
      position: asInteger(row.position, "inbox.send.position"),
      from: asString(row.from, "inbox.send.from"),
      to: asString(row.to, "inbox.send.to"),
      text,
      sentAt: asString(row.sent_at, "inbox.send.sent_at"),
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
 * The browser supplies the message text and nothing else. The thread comes
 * from the route this action was bound to, the recipient is read back from the
 * server's own recipient-scoped projection at submit time, and the sender is
 * never sent at all — the API derives it from the bearer this server holds. A
 * recipient a browser could edit would be a claimed identity, so there is no
 * form field for one.
 */
export async function sendInboxMessage(threadId: string, text: string): Promise<InboxSendState> {
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
    return refused("Sending is not available because this server has no API credential.", text);
  }
  let recipient: string;
  try {
    recipient = (await loadInboxCorrespondent(threadId)).recipient;
  } catch {
    return refused("This thread's other participant could not be read, so nothing was sent.", text);
  }
  const commandId = randomUUID();
  try {
    const result = await boundedMutation(
      `${instanceIdentity().baseUrl}/v1/inbox/messages`,
      commandHeaders(credential, commandId, SURFACE),
      JSON.stringify({ text: message, thread_id: threadId, to: recipient })
    );
    return sentFrom(result, threadId, message);
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
