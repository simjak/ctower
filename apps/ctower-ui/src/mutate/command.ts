import { randomBytes } from "node:crypto";
import { asArray, asInteger, asRecord, asString, PayloadRefusal } from "@/read/json";

/**
 * What every server-authoritative command from this surface has in common.
 *
 * A control here sends intent and nothing else. The bearer is read from the
 * server process environment and attached to a server-side request, so no
 * browser payload on this surface carries it; the payload names no actor,
 * project, custody or authorization fact, because the API derives all of those
 * from the credential it validates. One `Idempotency-Key` is minted before the
 * first attempt and reused unchanged by every bounded retry.
 *
 * The readers below refuse any response that is not exactly the authored
 * contract shape. A control therefore cannot render a field the server did not
 * send, and a refusal reaches the operator as the server's own validated
 * `detail` sentence rather than as a parser's complaint.
 */

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;

const LOWEST_REFUSAL_STATUS = 400;
const HIGHEST_REFUSAL_STATUS = 599;

export function isUuid(value: string): boolean {
  return UUID.test(value);
}

/**
 * One correlated command context. The server rebinds tenant and actor from the
 * authenticated principal, so the values here identify the surface that asked,
 * never a claimed identity.
 */
function telemetry(commandId: string, surface: string): Record<string, string | number> {
  return {
    schema: "ctower.telemetry-context/v1",
    trace_id: randomBytes(16).toString("hex"),
    span_id: randomBytes(8).toString("hex"),
    trace_flags: 0,
    correlation_id: commandId,
    causation_id: commandId,
    command_id: commandId,
    tenant_id: surface,
    actor_id: surface,
  };
}

/** The headers one bounded mutation sends, including the key every retry reuses. */
export function commandHeaders(
  credential: string,
  commandId: string,
  surface: string
): Record<string, string> {
  return {
    Accept: "application/json, application/problem+json",
    Authorization: `Bearer ${credential}`,
    "Content-Type": "application/json",
    "Idempotency-Key": commandId,
    "X-Ctower-Telemetry-Context": JSON.stringify(telemetry(commandId, surface)),
  };
}

/**
 * A record carrying exactly the authored fields: no more, and none missing.
 *
 * An unexpected key is refused rather than ignored, so a response from a
 * different operation cannot be rendered as this one.
 */
export function exactRecord(
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

export function uuidField(value: unknown, field: string): string {
  const parsed = asString(value, field);
  if (!UUID.test(parsed)) {
    throw new PayloadRefusal(field, "a UUID");
  }
  return parsed;
}

/**
 * The one sentence a refusal is allowed to put on the screen.
 *
 * The whole problem document is validated first: a body that is not a problem
 * document — a proxy's `text/plain`, or nothing at all — refuses here, and the
 * caller says so in its own plain words instead of quoting bytes it could not
 * read.
 */
export function problemSentence(value: unknown, field: string): string {
  const fields = ["code", "detail", "status", "title", "type"] as const;
  const optional = ["command_id", "current_version", "prohibited_classes", "unmet_facts"] as const;
  const row = exactRecord(value, field, fields, optional);
  asString(row.code, `${field}.code`);
  const status = asInteger(row.status, `${field}.status`);
  if (status < LOWEST_REFUSAL_STATUS || status > HIGHEST_REFUSAL_STATUS) {
    throw new PayloadRefusal(`${field}.status`, "an HTTP refusal status");
  }
  asString(row.title, `${field}.title`);
  asString(row.type, `${field}.type`);
  if (Object.hasOwn(row, "command_id") && row.command_id !== null) {
    uuidField(row.command_id, `${field}.command_id`);
  }
  if (Object.hasOwn(row, "current_version") && row.current_version !== null) {
    asInteger(row.current_version, `${field}.current_version`);
  }
  for (const list of ["prohibited_classes", "unmet_facts"] as const) {
    if (Object.hasOwn(row, list)) {
      asArray(row[list], `${field}.${list}`).forEach((item, index) =>
        asString(item, `${field}.${list}[${index.toString()}]`)
      );
    }
  }
  return asString(row.detail, `${field}.detail`);
}
