/**
 * The one boundary-crossing chokepoint in this app (O10).
 *
 * The repository coding standard forbids single-shot calls across a process or
 * network boundary, loopback services included. Both crossings this app makes
 * live here — `boundedRead` for HTTP and `boundedProcess` for a child process —
 * and they share one policy. This is the only place in `apps/` that names
 * `fetch` or `node:child_process`; `tests/repository/
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
 * 5. Idempotency before retrying a mutation — `boundedMutation` requires the
 *    caller to provide the one generated `Idempotency-Key` that is reused for
 *    every attempt. The read and process helpers remain closed: HTTP reads are
 *    `GET`, and the process reader takes a named inspection from the closed
 *    grammar in `read/commands.ts` rather than caller argv.
 */

import { execFile } from "node:child_process";
import { invocationFor } from "./commands";
import type { Inspection } from "./commands";

export type FailureClass = "transient" | "permanent";

export interface ClassifiedFailure {
  readonly failureClass: FailureClass;
  readonly detail: string;
  /** The status the API answered, when the failure came from one. */
  readonly status?: number;
}

/** What a caller learns when a read does not produce a payload. */
export interface ReadFailure {
  readonly reason: string;
  readonly failureClass: FailureClass;
  readonly attempts: number;
  readonly elapsedMs: number;
  /**
   * The HTTP status behind the failure, when there was one. A screen may not
   * parse it back out of `reason`: "not allowed to look" and "could not reach"
   * are different things to say to an operator, and a substring match on prose
   * is not a sound way to tell them apart.
   */
  readonly status: number | null;
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

/** A typed non-success response from the server-owned mutation path. */
export class MutationRefused extends Error {
  public readonly status: number;
  public readonly document: unknown;

  public constructor(status: number, document: unknown) {
    super(`the mutation API answered ${status.toString()}`);
    this.name = "MutationRefused";
    this.status = status;
    this.document = document;
  }
}

let exhaustionCount = 0;

/** Observable exhaustion tally for this process; read by the health surface. */
export function exhaustions(): number {
  return exhaustionCount;
}

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

function classifyStatus(
  status: number,
  operation: "read" | "mutation" = "read"
): ClassifiedFailure {
  return {
    failureClass: RETRYABLE_STATUS.has(status) ? "transient" : "permanent",
    detail: `the ${operation} API answered ${status.toString()}`,
    status,
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
    status: classified.status ?? null,
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

/**
 * A failure the loop already built, folded back into a classification.
 *
 * The status has to survive this fold. A screen tells "we are not allowed to
 * look" from "we could not reach it" by the status, and re-deriving it by
 * matching prose in `reason` is not a sound way to tell an operator which of
 * those two happened — this dropped it before, so a 401 reached the Board as a
 * generic unreachable-source block.
 */
export function reclassified(spent: ReadFailure): ClassifiedFailure {
  return {
    failureClass: spent.failureClass,
    detail: spent.reason,
    ...(spent.status === null ? {} : { status: spent.status }),
  };
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
 * A refusal body, read without letting the read decide the classification.
 *
 * Only a success carries a contract-shaped payload. A refusal may carry a
 * problem document, a proxy's `text/plain` sentence, or nothing at all, and
 * which of those arrived says nothing about whether the status is retryable.
 * Parsing it eagerly used to throw a `SyntaxError` before the status reached
 * `classifyStatus`, so a proxy 503 was classified permanent and the mutation
 * stopped after one attempt; the text is preserved instead, and the caller's
 * problem-document validator refuses it as the non-document it is.
 */
function refusalDocument(body: string): unknown {
  try {
    const parsed: unknown = JSON.parse(body);
    return parsed;
  } catch {
    return body;
  }
}

async function mutationAttempt(
  url: string,
  headers: Readonly<Record<string, string>>,
  body: string,
  timeoutMs: number
): Promise<unknown> {
  const response = await fetch(url, {
    method: "POST",
    headers,
    body,
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
  const answered = await response.text();
  if (!response.ok) {
    throw new MutationRefused(response.status, refusalDocument(answered));
  }
  const payload: unknown = JSON.parse(answered);
  return payload;
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
      last = error instanceof ReadRefused ? reclassified(error.failure) : classifyThrown(error);
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

/**
 * Call one server-authoritative mutation under the same bounded policy.
 *
 * The serialized body and `Idempotency-Key` are supplied once and then reused
 * unchanged on every retry. Retryable HTTP response statuses re-enter the
 * bounded loop; a permanent server problem document is terminal and the caller
 * renders its human `detail` rather than treating it as transport noise.
 */
export async function boundedMutation(
  url: string,
  headers: Readonly<Record<string, string>>,
  body: string,
  bounds: ReadBounds = RECORD_READ_BOUNDS
): Promise<unknown> {
  const idempotencyKey = headers["Idempotency-Key"];
  if (idempotencyKey === undefined || idempotencyKey === "") {
    throw new TypeError("a bounded mutation requires an Idempotency-Key");
  }
  const startedAt = Date.now();
  let attempts = 0;
  let last: ClassifiedFailure = {
    failureClass: "transient",
    detail: "the mutation made no attempt",
  };

  while (attempts < bounds.maxAttempts) {
    const remainingBefore = bounds.maxElapsedMs - (Date.now() - startedAt);
    if (remainingBefore <= 0) {
      break;
    }
    attempts += 1;
    try {
      return await mutationAttempt(
        url,
        headers,
        body,
        Math.min(bounds.attemptTimeoutMs, remainingBefore)
      );
    } catch (error: unknown) {
      if (error instanceof MutationRefused) {
        last = classifyStatus(error.status, "mutation");
        if (last.failureClass === "permanent") {
          throw error;
        }
      } else {
        last = error instanceof ReadRefused ? reclassified(error.failure) : classifyThrown(error);
      }
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

/** Child-process reads: a tighter attempt bound than HTTP, same policy shape. */
export const PROCESS_READ_BOUNDS: ReadBounds = {
  attemptTimeoutMs: 6_000,
  maxAttempts: 3,
  maxElapsedMs: 15_000,
  baseDelayMs: 100,
  maxDelayMs: 1_500,
};

interface ChildOutcome {
  readonly stdout: string;
  readonly failure: ClassifiedFailure | null;
}

function classifyChild(error: Error): ClassifiedFailure {
  const detail = error as Error & {
    readonly killed?: unknown;
    readonly code?: unknown;
    readonly path?: unknown;
  };
  if (detail.killed === true || detail.code === "ETIMEDOUT") {
    return { failureClass: "transient", detail: "the process read timed out" };
  }
  if (detail.code === "ENOENT") {
    const path = typeof detail.path === "string" ? detail.path : "the command";
    return { failureClass: "permanent", detail: `${path} is not installed` };
  }
  return { failureClass: "permanent", detail: error.message };
}

function runChild(
  executable: string,
  args: readonly string[],
  maxBytes: number,
  timeoutMs: number
): Promise<ChildOutcome> {
  return new Promise((resolve) => {
    execFile(
      executable,
      [...args],
      {
        timeout: timeoutMs,
        killSignal: "SIGKILL",
        maxBuffer: maxBytes,
        windowsHide: true,
        shell: false,
      },
      (error, stdout) => {
        resolve(
          error === null ? { stdout, failure: null } : { stdout, failure: classifyChild(error) }
        );
      }
    );
  });
}

/**
 * Read one inspection's stdout under the same bounded policy as HTTP.
 *
 * The caller names an inspection; `read/commands.ts` builds the argv from a
 * closed grammar and resolves the tool to an absolute path. No caller supplies
 * argv, so a mutating subcommand is not expressible here — the read-only
 * guarantee is structural rather than a convention every call site must keep.
 *
 * A non-zero exit is classified permanent — an inspection tool that refuses is
 * answering, not failing — while a timeout or kill is transient and retried
 * under the deadline.
 */
export async function boundedProcess(
  inspection: Inspection,
  bounds: ReadBounds = PROCESS_READ_BOUNDS
): Promise<string> {
  const invocation = invocationFor(inspection);
  const startedAt = Date.now();
  let attempts = 0;
  let last: ClassifiedFailure = {
    failureClass: "transient",
    detail: "the process read made no attempt",
  };
  const label = `${invocation.label} (${invocation.tool})`;

  while (attempts < bounds.maxAttempts) {
    const remainingBefore = bounds.maxElapsedMs - (Date.now() - startedAt);
    if (remainingBefore <= 0) {
      break;
    }
    attempts += 1;
    const outcome = await runChild(
      invocation.executable,
      invocation.args,
      invocation.maxBytes,
      Math.min(bounds.attemptTimeoutMs, remainingBefore)
    );
    if (outcome.failure === null) {
      return outcome.stdout;
    }
    last = outcome.failure;
    if (last.failureClass === "permanent") {
      throw new ReadRefused(failure(last, attempts, Date.now() - startedAt, false));
    }
    const remainingAfter = bounds.maxElapsedMs - (Date.now() - startedAt);
    if (attempts >= bounds.maxAttempts || remainingAfter <= 0) {
      break;
    }
    await pause(backoffMs(attempts, bounds, remainingAfter));
  }

  const spent = failure(last, attempts, Date.now() - startedAt, true);
  countExhaustion(label, spent);
  throw new ReadExhausted(spent);
}
