import { randomBytes, randomUUID } from "node:crypto";
import { boundedMutation, MutationRefused, ReadRefused } from "@/read/bounded";
import { instanceIdentity } from "@/read/httpRecordAdapter";
import { asArray, asInteger, asMember, asRecord, asString, PayloadRefusal } from "@/read/json";
import type { InboxPromotionState } from "./types";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;
const OUTCOMES = ["ticket_created", "ticket_linked"] as const;
const DURABILITY = ["accepted", "durability_pending"] as const;

function telemetry(commandId: string): Record<string, string | number> {
  return {
    schema: "ctower.telemetry-context/v1",
    trace_id: randomBytes(16).toString("hex"),
    span_id: randomBytes(8).toString("hex"),
    trace_flags: 0,
    correlation_id: commandId,
    causation_id: commandId,
    command_id: commandId,
    tenant_id: "ctower-ui-promotion",
    actor_id: "ctower-ui-promotion",
  };
}

function exactRecord(
  value: unknown,
  field: string,
  required: readonly string[],
  optional: readonly string[] = []
): Record<string, unknown> {
  const row = asRecord(value, field);
  const allowed = [...required, ...optional];
  const unexpected = Object.keys(row).filter((key) => !allowed.includes(key));
  const missing = required.filter((key) => !Object.hasOwn(row, key));
  if (unexpected.length > 0 || missing.length > 0) {
    throw new PayloadRefusal(field, `the authored ${allowed.join(", ")} fields`);
  }
  return row;
}

function uuid(value: unknown, field: string): string {
  const parsed = asString(value, field);
  if (!UUID.test(parsed)) {
    throw new PayloadRefusal(field, "a UUID");
  }
  return parsed;
}

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
  uuid(row.command_id, "inbox.promotion.command_id");
  asMember(row.durability_state, "inbox.promotion.durability_state", DURABILITY);
  const eventIds = asArray(row.event_ids, "inbox.promotion.event_ids");
  if (eventIds.length < 1 || eventIds.length > 2) {
    throw new PayloadRefusal("inbox.promotion.event_ids", "one or two event UUIDs");
  }
  eventIds.forEach((eventId, index) => {
    uuid(eventId, `inbox.promotion.event_ids[${index.toString()}]`);
  });
  const returnedThreadId = uuid(row.thread_id, "inbox.promotion.thread_id");
  if (returnedThreadId !== expectedThreadId) {
    throw new PayloadRefusal("inbox.promotion.thread_id", "the requested inbox thread UUID");
  }
  if (asInteger(row.thread_version, "inbox.promotion.thread_version") < 3) {
    throw new PayloadRefusal("inbox.promotion.thread_version", "an integer of at least 3");
  }
  return {
    kind: "promoted",
    outcome: asMember(row.outcome, "inbox.promotion.outcome", OUTCOMES),
    ticketId: uuid(row.ticket_id, "inbox.promotion.ticket_id"),
  };
}

function problemSentence(value: unknown): string {
  const fields = ["code", "detail", "status", "title", "type"] as const;
  const optional = ["command_id", "current_version", "prohibited_classes", "unmet_facts"] as const;
  const row = exactRecord(value, "inbox.promotion.problem", fields, optional);
  asString(row.code, "inbox.promotion.problem.code");
  const status = asInteger(row.status, "inbox.promotion.problem.status");
  if (status < 400 || status > 599) {
    throw new PayloadRefusal("inbox.promotion.problem.status", "an HTTP refusal status");
  }
  asString(row.title, "inbox.promotion.problem.title");
  asString(row.type, "inbox.promotion.problem.type");
  if (Object.hasOwn(row, "command_id") && row.command_id !== null) {
    uuid(row.command_id, "inbox.promotion.problem.command_id");
  }
  if (Object.hasOwn(row, "current_version") && row.current_version !== null) {
    asInteger(row.current_version, "inbox.promotion.problem.current_version");
  }
  if (Object.hasOwn(row, "prohibited_classes")) {
    asArray(row.prohibited_classes, "inbox.promotion.problem.prohibited_classes").forEach(
      (value, index) =>
        asString(value, `inbox.promotion.problem.prohibited_classes[${index.toString()}]`)
    );
  }
  if (Object.hasOwn(row, "unmet_facts")) {
    asArray(row.unmet_facts, "inbox.promotion.problem.unmet_facts").forEach((value, index) =>
      asString(value, `inbox.promotion.problem.unmet_facts[${index.toString()}]`)
    );
  }
  return asString(row.detail, "inbox.promotion.problem.detail");
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
  if (!UUID.test(threadId) || (ticketId !== null && !UUID.test(ticketId))) {
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
      {
        Accept: "application/json, application/problem+json",
        Authorization: `Bearer ${credential}`,
        "Content-Type": "application/json",
        "Idempotency-Key": commandId,
        "X-Ctower-Telemetry-Context": JSON.stringify(telemetry(commandId)),
      },
      JSON.stringify(ticketId === null ? {} : { ticket_id: ticketId })
    );
    return promotionFrom(result, threadId);
  } catch (error: unknown) {
    if (error instanceof MutationRefused) {
      try {
        return unavailable(problemSentence(error.document));
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
