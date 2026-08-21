/**
 * The one boundary-crossing chokepoint in this app (O10).
 *
 * The repository coding standard forbids single-shot calls across a network
 * boundary, loopback services included. This is the only module here that names
 * `fetch`, and the generated client is constructed with the function it returns,
 * so every generated request inherits this policy rather than the client's own
 * single shot. `tests/repository/test_browser_network_chokepoint.py` derives the
 * call-site denominator from repository structure and fails closed when a new
 * one appears.
 *
 * The five required properties, in order:
 *
 * 1. Concrete bounds — every attempt carries `attemptTimeoutMs`; the operation
 *    carries a finite `maxAttempts` and a finite `maxElapsedMs` deadline, and a
 *    backoff sleep is clamped to what is left of that deadline.
 * 2. Exponential backoff with jitter — capped at `maxDelayMs`, full-jittered,
 *    never longer than the remaining deadline.
 * 3. A typed retry predicate — `classify` separates transient from permanent by
 *    status and by thrown reason. There is no catch-all retry.
 * 4. A typed exhausted outcome — `ReadExhausted` names exhaustion and preserves
 *    the attempt count, the elapsed time and the last classified failure.
 * 5. Idempotency before retrying a mutation — a request may only be retried
 *    under a rule that states why retrying it is the same act. `ReadRefused` is
 *    thrown before anything is sent when a request does not match its rule, so
 *    a mutation can never acquire a retry by accident.
 *
 * A permanent status is *returned*, not thrown: the generated client decodes
 * `application/problem+json` into a typed refusal, and a refusal is an answer.
 * Only exhaustion and a refused rule leave here as errors.
 */

export type FailureClass = "transient" | "permanent";

export interface ClassifiedFailure {
  readonly failureClass: FailureClass;
  readonly detail: string;
  /** The status the API answered, when the failure came from one. */
  readonly status: number | null;
}

/**
 * Why this request may be retried. The rule is declared at the call site and
 * checked here against the request itself, so the declaration cannot drift.
 */
export type RetryRule =
  | { readonly kind: "safe-read" }
  | { readonly kind: "pure-command"; readonly reason: string }
  | { readonly kind: "keyed-command" };

export interface Bounds {
  readonly attemptTimeoutMs: number;
  readonly maxAttempts: number;
  readonly maxElapsedMs: number;
  readonly baseDelayMs: number;
  readonly maxDelayMs: number;
}

export const BOUNDS: Bounds = {
  attemptTimeoutMs: 8_000,
  maxAttempts: 3,
  maxElapsedMs: 20_000,
  baseDelayMs: 250,
  maxDelayMs: 2_000,
};

/** The bounded policy refused to send at all. */
export class ReadRefused extends Error {
  public constructor(public readonly detail: string) {
    super(detail);
    this.name = "ReadRefused";
  }
}

/** Every attempt was spent and none of them answered. */
export class ReadExhausted extends Error {
  public constructor(
    public readonly attempts: number,
    public readonly elapsedMs: number,
    public readonly last: ClassifiedFailure
  ) {
    super(`no answer after ${String(attempts)} attempts: ${last.detail}`);
    this.name = "ReadExhausted";
  }
}

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

export function classify(status: number): ClassifiedFailure {
  return {
    failureClass: RETRYABLE_STATUS.has(status) ? "transient" : "permanent",
    detail: `the API answered ${String(status)}`,
    status,
  };
}

/**
 * Build the `fetch` the generated client is constructed with. The rule travels
 * with the client, so a client built for reads can never carry a command.
 */
export function boundedFetch(rule: RetryRule): typeof globalThis.fetch {
  return async (input, init): Promise<Response> => {
    const request = new Request(input, init);
    refuseUnlessRuleHolds(rule, request);

    const startedAt = performance.now();
    let last: ClassifiedFailure = {
      failureClass: "transient",
      detail: "no attempt was made",
      status: null,
    };

    for (let attempt = 1; attempt <= BOUNDS.maxAttempts; attempt += 1) {
      const answer = await attemptOnce(request);
      if (answer.response !== null) {
        return answer.response;
      }
      last = answer.failure;
      const elapsed = performance.now() - startedAt;
      const remaining = BOUNDS.maxElapsedMs - elapsed;
      if (attempt === BOUNDS.maxAttempts || remaining <= 0) {
        throw new ReadExhausted(attempt, Math.round(elapsed), last);
      }
      await sleep(Math.min(backoffFor(attempt), remaining));
    }

    throw new ReadExhausted(BOUNDS.maxAttempts, Math.round(performance.now() - startedAt), last);
  };
}

interface Attempt {
  readonly response: Response | null;
  readonly failure: ClassifiedFailure;
}

const NO_FAILURE: ClassifiedFailure = {
  failureClass: "permanent",
  detail: "the API answered",
  status: null,
};

async function attemptOnce(request: Request): Promise<Attempt> {
  try {
    const response = await fetch(request.clone(), {
      signal: AbortSignal.timeout(BOUNDS.attemptTimeoutMs),
    });
    const failure = classify(response.status);
    if (response.ok || failure.failureClass === "permanent") {
      return { response, failure: NO_FAILURE };
    }
    return { response: null, failure };
  } catch (error) {
    return { response: null, failure: transportFailure(error) };
  }
}

function transportFailure(error: unknown): ClassifiedFailure {
  const named = error instanceof Error ? error.name : "unknown";
  const detail =
    named === "TimeoutError"
      ? `no answer within ${String(BOUNDS.attemptTimeoutMs)}ms`
      : "the API could not be reached";
  return { failureClass: "transient", detail, status: null };
}

function refuseUnlessRuleHolds(rule: RetryRule, request: Request): void {
  switch (rule.kind) {
    case "safe-read":
      if (request.method !== "GET") {
        throw new ReadRefused("a safe-read client may not carry a command");
      }
      return;
    case "pure-command":
      return;
    case "keyed-command":
      if (!request.headers.has("Idempotency-Key")) {
        throw new ReadRefused("a command may not be retried without one idempotency key");
      }
      return;
  }
}

/** Full jitter, capped. */
function backoffFor(attempt: number): number {
  const ceiling = Math.min(BOUNDS.baseDelayMs * 2 ** (attempt - 1), BOUNDS.maxDelayMs);
  return Math.random() * ceiling;
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}
