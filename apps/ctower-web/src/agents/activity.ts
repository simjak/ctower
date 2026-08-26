import type { TicketSession } from "@ctower/client";
import { livenessOf } from "./liveness";
import type { MarkName } from "../ui/marks";

/**
 * What a set of recorded runs is allowed to say about itself.
 *
 * Everything here is arithmetic over facts the record already holds — a count,
 * a sum, a share — and nothing here reaches for a fact it does not have. Three
 * of the figures the agent home asks for are missing on purpose rather than by
 * omission, and the screen draws each of them as missing:
 *
 * - **whose runs these are.** A recorded run carries the seat that ran it; an
 *   agent is named somewhere else entirely, and nothing joins the two. So these
 *   figures are the team's, never one agent's, and the tab says so in a
 *   sentence rather than in a footnote.
 * - **cached tokens.** A run records what went in and what came out. There is
 *   no third number.
 * - **what it cost.** No price is recorded against any model anywhere, so a
 *   total in money would be this screen's invention, not the record's fact.
 */

/** Volume and recency: how much work is recorded, and when it last moved. */
export interface Activity {
  readonly runs: number;
  readonly open: number;
  /** The newest start the record holds, already in words. */
  readonly lastStarted: string | null;
}

/** One bucket of the closed status vocabulary, and how many runs are in it. */
export interface StatusCount {
  readonly mark: MarkName | null;
  readonly word: string;
  readonly runs: number;
}

/**
 * Delivery, with its own denominator carried beside it. A run that finished
 * with no result recorded is counted apart rather than folded into either side:
 * it is neither a success nor a failure, and putting it in one of them would
 * move the share by a fact nobody recorded.
 */
export interface Delivery {
  readonly delivered: number;
  readonly finished: number;
  readonly unrecorded: number;
}

/** What was spent in tokens, and how much of the work that figure covers. */
export interface Usage {
  readonly input: number;
  readonly output: number;
  readonly counted: number;
}

export function activityOf(runs: readonly TicketSession[]): Activity {
  // By the instant each start denotes, not by the text it is written in: the
  // record is free to write the same moment with a different offset, and two
  // spellings of one instant do not sort against each other as strings.
  let newest: string | null = null;
  for (const run of runs) {
    if (newest === null || Date.parse(run.started_at) > Date.parse(newest)) {
      newest = run.started_at;
    }
  }
  return {
    runs: runs.length,
    open: runs.filter((run) => run.closed_at === null).length,
    lastStarted: newest === null ? null : when(newest),
  };
}

/**
 * Runs grouped by the one status vocabulary this console has, largest bucket
 * first.
 *
 * Sorting a *list* of records would overrule the order the record returned
 * them in. This is not that list: the record declares no order over buckets it
 * never made, so the ordering is the aggregate's own fact — how many are in it
 * — with the vocabulary's own order breaking a tie so the same data always
 * draws the same way.
 */
export function statusesOf(runs: readonly TicketSession[]): readonly StatusCount[] {
  const buckets = new Map<string, StatusCount>();
  for (const run of runs) {
    const { mark, word } = livenessOf(run);
    const seen = buckets.get(word);
    buckets.set(word, { mark, word, runs: (seen?.runs ?? 0) + 1 });
  }
  const order = [...buckets.keys()];
  return [...buckets.values()].sort(
    (left, right) => right.runs - left.runs || order.indexOf(left.word) - order.indexOf(right.word)
  );
}

export function deliveryOf(runs: readonly TicketSession[]): Delivery {
  const closed = runs.filter((run) => run.closed_at !== null);
  return {
    delivered: closed.filter((run) => run.outcome === "delivered").length,
    finished: closed.filter((run) => run.outcome !== null).length,
    unrecorded: closed.filter((run) => run.outcome === null).length,
  };
}

export function usageOf(runs: readonly TicketSession[]): Usage {
  const counted = runs.filter((run) => run.tokens !== null);
  return {
    input: counted.reduce((total, run) => total + (run.tokens?.input_tokens ?? 0), 0),
    output: counted.reduce((total, run) => total + (run.tokens?.output_tokens ?? 0), 0),
    counted: counted.length,
  };
}

/**
 * A moment, in words a person reads.
 *
 * The record keeps an instant to the microsecond, which is the right thing for
 * a record and the wrong thing for a screen — an operator reads a date, not a
 * stamp. It is drawn in one fixed zone rather than the browser's, because two
 * people comparing the same screen have to be reading the same clock.
 */
const CLOCK = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "UTC",
});

export function when(instant: string): string | null {
  const at = new Date(instant);
  return Number.isNaN(at.getTime()) ? null : `${CLOCK.format(at)} UTC`;
}
