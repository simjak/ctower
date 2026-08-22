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
 * 1. Concrete bounds — every attempt carries `attemptTimeoutMs` *or the rest of
 *    the deadline, whichever is smaller*; the operation carries a finite
 *    `maxAttempts` and a finite `maxElapsedMs` deadline, and both the attempt
 *    and the backoff sleep are clamped to what is left of it. Clamping only the
 *    sleep is not a wall bound: an attempt starting with a small remainder
 *    would run the full per-attempt timeout past the advertised deadline.
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
 * Only exhaustion, a refused rule, and a refusal by the serving process itself
 * leave here as errors.
 *
 * That last one is why this module also knows about the session token. The
 * development server holds the operator credential, so it admits nobody without
 * the token it printed at startup; this is where that token is attached and
 * where its refusal is turned into a typed outcome instead of a mystery `401`.
 * The token is admission to that process and is stripped before anything is
 * proxied — it is never an API bearer and never travels as one.
 */

import { recordExhaustion } from "./observe";
import {
  ADMISSION_PATH,
  forgetSession,
  GATE_HEADER,
  keepSession,
  SESSION_HEADER,
  sessionToken,
} from "./session";

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
  | { readonly kind: "keyed-command" }
  | { readonly kind: "unrepeatable-command"; readonly reason: string };

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

/** The server that serves this app does not admit this browser. */
export class SessionRefused extends Error {
  public constructor() {
    super("this server no longer admits this browser's session token");
    this.name = "SessionRefused";
  }
}

/** The bounded policy refused to send at all. */
export class ReadRefused extends Error {
  public constructor(public readonly detail: string) {
    super(detail);
    this.name = "ReadRefused";
  }
}

/**
 * Every attempt was spent and none of them answered.
 *
 * Built only through `exhausted()` below, so that counting and logging cannot
 * be skipped by an exit that forgets — O10 requires exhaustion to be observed,
 * not just thrown.
 */
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

/** The one constructor for exhaustion: observe, then throw. */
function exhausted(attempts: number, elapsedMs: number, last: ClassifiedFailure): ReadExhausted {
  recordExhaustion({
    attempts,
    elapsedMs,
    failureClass: last.failureClass,
    detail: last.detail,
    status: last.status,
  });
  return new ReadExhausted(attempts, elapsedMs, last);
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
    admit(request);

    const maxAttempts = attemptsFor(rule);
    const startedAt = performance.now();
    let last: ClassifiedFailure = {
      failureClass: "transient",
      detail: "no attempt was made",
      status: null,
    };

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      // The deadline binds the attempt, not just the gap between attempts. An
      // attempt that starts with 10ms left may not install a 8s timeout and run
      // past the wall bound this policy advertises, so the per-attempt budget is
      // whichever of `attemptTimeoutMs` and the remaining deadline is smaller.
      const budget = Math.min(BOUNDS.attemptTimeoutMs, BOUNDS.maxElapsedMs - since(startedAt));
      if (budget <= 0) {
        throw exhausted(attempt - 1, Math.round(since(startedAt)), last);
      }
      const answer = await attemptOnce(request, budget);
      if (answer.response !== null) {
        refuseIfGated(answer.response);
        return answer.response;
      }
      last = answer.failure;
      const remaining = BOUNDS.maxElapsedMs - since(startedAt);
      if (attempt === maxAttempts || remaining <= 0) {
        throw exhausted(attempt, Math.round(since(startedAt)), last);
      }
      await sleep(Math.min(backoffFor(attempt), remaining));
    }

    throw exhausted(maxAttempts, Math.round(since(startedAt)), last);
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

/**
 * Present this browser's admission token to the server that holds the operator
 * credential. It is the server's own and goes no further: the server strips it
 * before proxying, so it is never an API bearer and never travels as one.
 */
function admit(request: Request): void {
  const token = sessionToken();
  if (token !== null && !request.headers.has(SESSION_HEADER)) {
    request.headers.set(SESSION_HEADER, token);
  }
}

/**
 * The server refused on its own behalf and the API was never asked, so this is
 * neither a refusal by ctower nor a contract fault. Retrying would only spend
 * attempts on a token that is now wrong — a restarted server mints a new one —
 * so the held token is dropped and the screen is told to ask for it again.
 */
function refuseIfGated(response: Response): void {
  if (response.headers.get(GATE_HEADER) !== "refused") {
    return;
  }
  forgetSession();
  throw new SessionRefused();
}

/**
 * Offer a token to the server before anything is built on it, so a mistyped
 * paste is answered on the gate screen rather than as a mystery refusal four
 * screens later. Bounded like every other crossing here.
 */
export async function probeAdmission(token: string): Promise<boolean> {
  const offered = token.trim();
  if (offered === "") {
    return false;
  }
  const probe = boundedFetch({ kind: "safe-read" });
  try {
    const response = await probe(ADMISSION_PATH, { headers: { [SESSION_HEADER]: offered } });
    if (!response.ok) {
      return false;
    }
  } catch {
    return false;
  }
  keepSession(offered);
  return true;
}

async function attemptOnce(request: Request, budgetMs: number): Promise<Attempt> {
  try {
    const response = await fetch(request.clone(), {
      signal: AbortSignal.timeout(budgetMs),
    });
    const failure = classify(response.status);
    if (response.ok || failure.failureClass === "permanent") {
      return { response, failure: NO_FAILURE };
    }
    return { response: null, failure };
  } catch (error) {
    return { response: null, failure: transportFailure(error, budgetMs) };
  }
}

function transportFailure(error: unknown, budgetMs: number): ClassifiedFailure {
  const named = error instanceof Error ? error.name : "unknown";
  const detail =
    named === "TimeoutError"
      ? `no answer within ${String(Math.round(budgetMs))}ms`
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
    case "unrepeatable-command":
      // The mirror of the keyed rule. A command that *does* carry a key has a
      // retry available to it and must claim it, rather than spending its one
      // attempt under a rule written for commands the contract gives no key.
      if (request.headers.has("Idempotency-Key")) {
        throw new ReadRefused("a keyed command may not be sent as an unrepeatable one");
      }
      return;
  }
}

/**
 * How many attempts this rule may spend.
 *
 * O10 requires `maxAttempts` to be finite, and one is finite. A command the
 * authored contract gives no idempotency key cannot be retried at all: the
 * second send is a second act, the tower would record it as one, and the
 * operator would have no way to tell the two apart afterwards. So the bound
 * that keeps that command honest is the smallest one there is, and a transient
 * failure leaves here as exhaustion after a single attempt rather than as a
 * silent duplicate.
 */
function attemptsFor(rule: RetryRule): number {
  return rule.kind === "unrepeatable-command" ? 1 : BOUNDS.maxAttempts;
}

/** Full jitter, capped. */
function backoffFor(attempt: number): number {
  const ceiling = Math.min(BOUNDS.baseDelayMs * 2 ** (attempt - 1), BOUNDS.maxDelayMs);
  return Math.random() * ceiling;
}

function since(startedAt: number): number {
  return performance.now() - startedAt;
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}
