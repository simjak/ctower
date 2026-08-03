import { ReadExhausted, ReadRefused } from "./bounded";
import type { ReadFailure } from "./bounded";
import type { Reading } from "./interface";

/**
 * The one place a thrown source failure becomes a `Reading`.
 *
 * Every source — HTTP, file, process — returns through here, so no source can
 * hand a screen an empty value in place of a failure. A bounded refusal or
 * exhaustion keeps its typed facts; anything else is classified permanent and
 * still names itself.
 */
export function readFailureOf(error: unknown): ReadFailure {
  if (error instanceof ReadExhausted || error instanceof ReadRefused) {
    return error.failure;
  }
  return {
    reason: error instanceof Error ? error.message : "the read did not complete",
    failureClass: "permanent",
    attempts: 1,
    elapsedMs: 0,
  };
}

export async function reading<T>(load: () => Promise<T>): Promise<Reading<T>> {
  try {
    return { state: "present", value: await load() };
  } catch (error: unknown) {
    return { state: "unavailable", failure: readFailureOf(error) };
  }
}
