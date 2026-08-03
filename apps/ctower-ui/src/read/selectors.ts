import type { FutureSource, Reading } from "./interface";

/**
 * Ranking over readings that may be partly unavailable.
 *
 * A selector that picks "the most recent" from a fan-out is only sound if it
 * saw every candidate. Round-2 review found both of this app's selectors
 * dropping unavailable inputs before ranking: the failed stream could have been
 * the newest, so the survivor was being called `most recent` on evidence that
 * did not exist.
 *
 * The rule here is that a missing input is never silently discarded. Either the
 * ranking is complete, or the caller gets a typed incomplete outcome that names
 * how many inputs went unread and why — and the screens render that, they do
 * not swallow it.
 *
 * This module is deliberately pure and dependency-free at runtime (its only
 * import is a type, which is erased), so `tests/repository/
 * test_reading_selectors.py` can execute it directly and drive every mixed
 * present/unavailable branch deterministically.
 */

/** A choice made from a fan-out, carrying how much of the fan-out was unread. */
export interface Ranked<T> {
  readonly chosen: T;
  /** Inputs that did not answer. Above zero, the ranking is provisional. */
  readonly unread: number;
  /** Inputs considered in total, so a reader can size the gap. */
  readonly considered: number;
  /** The first failure observed, verbatim; `null` only when `unread` is zero. */
  readonly reason: string | null;
}

export interface Candidate<T> {
  /** The reading for this candidate; `unavailable` means it cannot be ranked. */
  readonly reading: Reading<T>;
  /** The value used to order this candidate, when it answered. */
  readonly orderBy: string;
}

/**
 * What a wholly-empty fan-out declares. It is the surface's one absence type,
 * imported as a type only so this module stays runtime-pure.
 */
export type AbsentSource = FutureSource;

function firstFailure<T>(candidates: readonly Candidate<T>[]): string | null {
  for (const candidate of candidates) {
    if (candidate.reading.state === "unavailable") {
      return candidate.reading.failure.reason;
    }
  }
  return null;
}

/**
 * Rank a fan-out, keeping unavailability visible.
 *
 * - every candidate unavailable → `unavailable`, carrying the first failure;
 * - no candidate present and none unavailable → `absent`, with `source`;
 * - otherwise → `present`, with `unread` counting the candidates that did not
 *   answer. `unread > 0` means the winner may not be the true winner, and the
 *   caller must say so on the surface.
 *
 * Ordering is by `orderBy` descending, then by the tie-break the caller
 * supplies through the candidate order, so the result is deterministic.
 */
export function rankCandidates<T>(
  candidates: readonly Candidate<T>[],
  source: AbsentSource
): Reading<Ranked<T>> {
  const unavailable = candidates.filter((item) => item.reading.state === "unavailable");
  const present = candidates.flatMap((item) =>
    item.reading.state === "present" ? [{ value: item.reading.value, orderBy: item.orderBy }] : []
  );

  if (present.length === 0) {
    const reason = firstFailure(candidates);
    return reason === null ? { state: "absent", source } : buildUnavailable(reason);
  }

  const ordered = [...present].sort((left, right) => right.orderBy.localeCompare(left.orderBy));
  const winner = ordered[0];
  if (winner === undefined) {
    return { state: "absent", source };
  }
  return {
    state: "present",
    value: {
      chosen: winner.value,
      unread: unavailable.length,
      considered: candidates.length,
      reason: firstFailure(candidates),
    },
  };
}

function buildUnavailable<T>(reason: string): Reading<Ranked<T>> {
  return {
    state: "unavailable",
    failure: { reason, failureClass: "permanent", attempts: 1, elapsedMs: 0, status: null },
  };
}

/**
 * A ranking whose *claim* cannot tolerate a gap.
 *
 * Some callers state a superlative — "the most recently created ticket" — with
 * nowhere to put a caveat, because the result is a redirect. For those, a
 * partial fan-out is not a provisional answer, it is an unsound one, so this
 * refuses rather than ranking.
 */
export function rankStrictly<T>(
  candidates: readonly Candidate<T>[],
  source: AbsentSource
): Reading<Ranked<T>> {
  const ranked = rankCandidates(candidates, source);
  if (ranked.state === "present" && ranked.value.unread > 0) {
    return buildUnavailable(
      `${ranked.value.unread.toString()} of ${ranked.value.considered.toString()} candidates did not answer, so the most-recent claim cannot be made: ${ranked.value.reason ?? "no reason recorded"}`
    );
  }
  return ranked;
}
