import type { TelemetryContext } from "@ctower/client";

/**
 * One telemetry context per request. The API requires the header and answers
 * `422` without it, so this is plumbing rather than a product fact — nothing
 * here is ever rendered.
 *
 * `crypto.randomUUID` is a secure-context API and this surface is served over
 * plain HTTP on a private address, so the identifiers are built from
 * `crypto.getRandomValues`, which is not. `tenant_id` and `actor_id` are this
 * client's own labels; the authority on the request is the credential the
 * development server attaches, never a claim made here.
 */
export function telemetry(): TelemetryContext {
  const correlation = uuid();
  return {
    schema: "ctower.telemetry-context/v1",
    trace_id: hex(16),
    span_id: hex(8),
    trace_flags: 0,
    correlation_id: correlation,
    causation_id: correlation,
    command_id: uuid(),
    tenant_id: "ctower-web",
    actor_id: "ctower-web",
  };
}

export function uuid(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const text = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return [
    text.slice(0, 8),
    text.slice(8, 12),
    text.slice(12, 16),
    text.slice(16, 20),
    text.slice(20),
  ].join("-");
}

function hex(byteLength: number): string {
  return [...crypto.getRandomValues(new Uint8Array(byteLength))]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
