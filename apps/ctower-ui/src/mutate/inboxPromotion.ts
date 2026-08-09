import { randomUUID } from "node:crypto";
import { boundedMutation, MutationRefused, ReadRefused } from "@/read/bounded";
import { instanceIdentity } from "@/read/httpRecordAdapter";
import { asArray, asInteger, asMember, PayloadRefusal } from "@/read/json";
import { commandHeaders, exactRecord, isUuid, problemSentence, uuidField } from "./command";
import type { InboxPromotionState } from "./types";

const OUTCOMES = ["ticket_created", "ticket_linked"] as const;
const DURABILITY = ["accepted", "durability_pending"] as const;
const SURFACE = "ctower-ui-promotion";

function promotionFrom(
  value: unknown,
  expectedThreadId: string
): Extract<InboxPromotionState, { readonly kind: "promoted" }> {
  const fields = [
    "command_id",
    "durability_state",
    "event_ids",
    "outcome",
    "thread_id",
    "thread_version",
    "ticket_id",
  ] as const;
  const row = exactRecord(value, "inbox.promotion", fields);
  uuidField(row.command_id, "inbox.promotion.command_id");
  asMember(row.durability_state, "inbox.promotion.durability_state", DURABILITY);
  const eventIds = asArray(row.event_ids, "inbox.promotion.event_ids");
  if (eventIds.length < 1 || eventIds.length > 2) {
    throw new PayloadRefusal("inbox.promotion.event_ids", "one or two event UUIDs");
  }
  eventIds.forEach((eventId, index) => {
    uuidField(eventId, `inbox.promotion.event_ids[${index.toString()}]`);
  });
  const returnedThreadId = uuidField(row.thread_id, "inbox.promotion.thread_id");
  if (returnedThreadId !== expectedThreadId) {
    throw new PayloadRefusal("inbox.promotion.thread_id", "the requested inbox thread UUID");
  }
  if (asInteger(row.thread_version, "inbox.promotion.thread_version") < 3) {
    throw new PayloadRefusal("inbox.promotion.thread_version", "an integer of at least 3");
  }
  return {
    kind: "promoted",
    outcome: asMember(row.outcome, "inbox.promotion.outcome", OUTCOMES),
    ticketId: uuidField(row.ticket_id, "inbox.promotion.ticket_id"),
  };
}

function unavailable(message: string): InboxPromotionState {
  return { kind: "refused", message };
}

/**
 * Request the already-authored promotion operation. This layer sends no actor,
 * project, custody, or authorization claim: the server derives all of those
 * from the bearer it validates. The browser never receives that bearer.
 */
export async function promoteInboxThread(
  threadId: string,
  ticketId: string | null
): Promise<InboxPromotionState> {
  if (!isUuid(threadId) || (ticketId !== null && !isUuid(ticketId))) {
    return unavailable("Choose a valid thread and ticket before promoting.");
  }
  const credential = process.env.CTOWER_UI_API_TOKEN;
  if (credential === undefined || credential === "") {
    return unavailable("Promotion is not available because this server has no API credential.");
  }
  const commandId = randomUUID();
  try {
    const result = await boundedMutation(
      `${instanceIdentity().baseUrl}/v1/inbox/threads/${encodeURIComponent(threadId)}/promotion`,
      commandHeaders(credential, commandId, SURFACE),
      JSON.stringify(ticketId === null ? {} : { ticket_id: ticketId })
    );
    return promotionFrom(result, threadId);
  } catch (error: unknown) {
    if (error instanceof MutationRefused) {
      try {
        return unavailable(problemSentence(error.document, "inbox.promotion.problem"));
      } catch {
        return unavailable("The server refused the promotion without a usable explanation.");
      }
    }
    if (error instanceof ReadRefused) {
      return unavailable("The server could not complete the promotion. Try again.");
    }
    return unavailable("The promotion could not reach the server. Try again.");
  }
}
