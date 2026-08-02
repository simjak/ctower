/**
 * The one network chokepoint in this boundary (O10).
 *
 * `docs/CODING_STANDARDS.md` forbids single-shot network calls, loopback
 * services included. Every record read goes through `boundedRead`, which is the
 * only place in `apps/` that names `fetch`; `tests/repository/
 * test_browser_network_chokepoint.py` derives the call-site denominator from
 * repository structure and fails closed when a new one appears.
 *
 * The five required properties, in order:
 *
 * 1. Concrete bounds — every attempt carries `attemptTimeoutMs`; the operation
 *    carries a finite `maxAttempts` and a finite `maxElapsedMs` deadline, and a
 *    backoff sleep is clamped to the remaining deadline.
 * 2. Exponential backoff with jitter — capped at `maxDelayMs`, full-jittered,
 *    never longer than what is left of the deadline.
 * 3. A typed retry predicate — `classify` distinguishes transient from
 *    permanent by status and by thrown reason; there is no catch-all retry.
 * 4. A typed exhausted outcome — `ReadExhausted` names exhaustion and preserves
 *    the attempt count, elapsed time and last classified failure; every
 *    exhaustion is counted and written once to stderr.
 * 5. Idempotency before retrying a mutation — satisfied by construction. This
 *    function issues `GET` and takes no body or method, so no mutation call
 *    site exists here to need a coordination key.
 */

export type FailureClass = "transient" | "permanent";

export interface ClassifiedFailure {
  readonly failureClass: FailureClass;
  readonly detail: string;
}

/** What a caller learns when a read does not produce a payload. */
export interface ReadFailure {
  readonly reason: string;
  readonly failureClass: FailureClass;
  readonly attempts: number;
  readonly elapsedMs: number;
}

export interface ReadBounds {
  readonly attemptTimeoutMs: number;
  readonly maxAttempts: number;
  readonly maxElapsedMs: number;
  readonly baseDelayMs: number;
  readonly maxDelayMs: number;
}

/** Loopback control-plane reads: fast attempts, a short whole-operation ceiling. */
export const RECORD_READ_BOUNDS: ReadBounds = {
  attemptTimeoutMs: 4_000,
  maxAttempts: 4,
  maxElapsedMs: 12_000,
  baseDelayMs: 120,
  maxDelayMs: 2_000,
};

/** A permanent refusal: the first classification was terminal, so no retry ran. */
export class ReadRefused extends Error {
  public readonly failure: ReadFailure;

  public constructor(failure: ReadFailure) {
    super(failure.reason);
    this.name = "ReadRefused";
    this.failure = failure;
  }
}

/** Both bounds spent. Carries the attempt count, elapsed time and last failure. */
export class ReadExhausted extends Error {
  public readonly failure: ReadFailure;

  public constructor(failure: ReadFailure) {
    super(failure.reason);
    this.name = "ReadExhausted";
    this.failure = failure;
  }
}

let exhaustionCount = 0;

/** Observable exhaustion tally for this process; read by the health surface. */
export function exhaustions(): number {
  return exhaustionCount;
}

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

function classifyStatus(status: number): ClassifiedFailure {
  return {
    failureClass: RETRYABLE_STATUS.has(status) ? "transient" : "permanent",
    detail: `the read API answered ${status.toString()}`,
  };
}

/**
 * The retry predicate. Timeouts, aborts and the `TypeError` the platform fetch
 * throws for a connection failure are transient; every other thrown reason is
 * terminal. There is no catch-all retry branch.
 */
function classifyThrown(error: unknown): ClassifiedFailure {
  if (
    error instanceof DOMException &&
    (error.name === "TimeoutError" || error.name === "AbortError")
  ) {
    return { failureClass: "transient", detail: "the read attempt timed out" };
  }
  if (error instanceof TypeError) {
    return {
      failureClass: "transient",
      detail: `the read could not reach the API (${error.message})`,
    };
  }
  if (error instanceof Error) {
    return { failureClass: "permanent", detail: error.message };
  }
  return { failureClass: "permanent", detail: "the read failed for an unnamed reason" };
}

function failure(
  classified: ClassifiedFailure,
  attempts: number,
  elapsedMs: number,
  exhausted: boolean
): ReadFailure {
  const bound = exhausted
    ? ` after ${attempts.toString()} attempts over ${elapsedMs.toString()}ms`
    : "";
  return {
    reason: `${classified.detail}${bound}`,
    failureClass: classified.failureClass,
    attempts,
    elapsedMs,
  };
}

/** Full-jittered exponential backoff, capped, and never past the deadline. */
function backoffMs(attempt: number, bounds: ReadBounds, remainingMs: number): number {
  const ceiling = Math.min(bounds.maxDelayMs, bounds.baseDelayMs * 2 ** (attempt - 1));
  return Math.min(remainingMs, Math.floor(Math.random() * ceiling));
}

function pause(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function countExhaustion(path: string, spent: ReadFailure): void {
  exhaustionCount += 1;
  process.stderr.write(
    `${JSON.stringify({
      event: "ctower-ui.read.exhausted",
      path,
      attempts: spent.attempts,
      elapsed_ms: spent.elapsedMs,
      failure_class: spent.failureClass,
      reason: spent.reason,
      exhaustions: exhaustionCount,
    })}\n`
  );
}

async function attempt(
  url: string,
  headers: Readonly<Record<string, string>>,
  timeoutMs: number
): Promise<unknown> {
  const response = await fetch(url, {
    method: "GET",
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new ReadRefused(failure(classifyStatus(response.status), 1, 0, false));
  }
  return await response.json();
}

/**
 * Read one JSON payload under the bounded policy.
 *
 * Throws `ReadRefused` on a permanent classification and `ReadExhausted` when
 * either bound is spent. It never returns an empty or defaulted value: a caller
 * cannot mistake a failed read for a recorded absence.
 */
export async function boundedRead(
  url: string,
  headers: Readonly<Record<string, string>>,
  bounds: ReadBounds = RECORD_READ_BOUNDS
): Promise<unknown> {
  const startedAt = Date.now();
  let attempts = 0;
  let last: ClassifiedFailure = {
    failureClass: "transient",
    detail: "the read made no attempt",
  };

  while (attempts < bounds.maxAttempts) {
    const remainingBefore = bounds.maxElapsedMs - (Date.now() - startedAt);
    if (remainingBefore <= 0) {
      break;
    }
    attempts += 1;
    try {
      return await attempt(url, headers, Math.min(bounds.attemptTimeoutMs, remainingBefore));
    } catch (error: unknown) {
      last =
        error instanceof ReadRefused
          ? { failureClass: error.failure.failureClass, detail: error.failure.reason }
          : classifyThrown(error);
      if (last.failureClass === "permanent") {
        throw new ReadRefused(failure(last, attempts, Date.now() - startedAt, false));
      }
    }
    const remainingAfter = bounds.maxElapsedMs - (Date.now() - startedAt);
    if (attempts >= bounds.maxAttempts || remainingAfter <= 0) {
      break;
    }
    await pause(backoffMs(attempts, bounds, remainingAfter));
  }

  const spent = failure(last, attempts, Date.now() - startedAt, true);
  countExhaustion(url, spent);
  throw new ReadExhausted(spent);
}
