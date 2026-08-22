import { CtowerClient, CtowerProblemError } from "@ctower/client";
import type { Problem } from "@ctower/client";
import { boundedFetch, ReadExhausted, ReadRefused, SessionRefused } from "./bounded";
import type { RetryRule } from "./bounded";
import { telemetry } from "./telemetry";

/**
 * The generated client, brought under this app's bounded policy.
 *
 * This is the only module in `apps/ctower-web` that value-imports
 * `@ctower/client`, and it never constructs one without a retry rule, so the
 * generated single shot is unreachable from a screen. Every path, parameter,
 * header and response type stays the generated operation table's: there is no
 * second copy of the contract here.
 *
 * The base URL is the app's own origin. The credential is attached by the
 * development server's proxy, so no `credential` is passed and the browser
 * holds none.
 */
function clientFor(rule: RetryRule): CtowerClient {
  return new CtowerClient({
    baseUrl: window.location.origin,
    telemetry,
    fetch: boundedFetch(rule),
  });
}

/** `exportCompanyBundle` is a `GET`; re-asking it is the same question. */
export const reads = clientFor({ kind: "safe-read" });

/**
 * `validateCompanyBundle` and `planCompanyBundle` compute an answer and record
 * nothing: replaying one produces the same digests and the same checks, which
 * is why a retry is the same act rather than a second one.
 */
export const computations = clientFor({
  kind: "pure-command",
  reason: "validate and plan record no fact; a replay returns the same digests",
});

/** `applyCompanyBundle` is retried only under the one idempotency key it was sent with. */
export const commands = clientFor({ kind: "keyed-command" });

/**
 * What a call produced. Four outcomes, and none of them collapses into
 * another: an answer, a typed refusal, silence, and an answer this client
 * cannot read. The last one exists because the alternative is a screen that
 * spins forever on a contract mismatch, which is what an unhandled decode
 * failure actually looks like to an operator.
 */
export type Answer<T> =
  | { readonly kind: "asking" }
  | { readonly kind: "answered"; readonly value: T }
  | { readonly kind: "refused"; readonly problem: Problem }
  | { readonly kind: "unreachable"; readonly detail: string }
  | { readonly kind: "malformed"; readonly detail: string };

export const ASKING: Answer<never> = { kind: "asking" };

/**
 * Run one call and name what came back. A typed refusal and an unreachable API
 * are different facts and never collapse into one error state: an operator who
 * cannot tell them apart cannot tell "ctower said no" from "ctower said
 * nothing".
 */
export async function ask<T>(call: () => Promise<T>): Promise<Answer<T>> {
  try {
    return { kind: "answered", value: await call() };
  } catch (error) {
    if (error instanceof CtowerProblemError) {
      return { kind: "refused", problem: error.problem };
    }
    if (error instanceof ReadExhausted) {
      return {
        kind: "unreachable",
        detail: `${error.last.detail} · ${String(error.attempts)} attempts`,
      };
    }
    if (error instanceof ReadRefused) {
      return { kind: "unreachable", detail: error.detail };
    }
    // The serving process refused before the API was asked. Nothing was
    // written, nothing was read, and the gate screen is already coming back.
    if (error instanceof SessionRefused) {
      return { kind: "unreachable", detail: error.message };
    }
    if (error instanceof TypeError) {
      return { kind: "malformed", detail: error.message };
    }
    throw error;
  }
}
