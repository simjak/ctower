/**
 * The one observation channel this browser has.
 *
 * O10 requires exhaustion to be **logged and counted**, not merely typed and
 * shown to whoever is looking at the screen. A browser has no log file and this
 * repository bans `console` in source, so the channel is the two things a
 * browser can honestly offer: a monotonic counter and a bounded record, both
 * readable, plus a DOM event so anything that wants to forward them can.
 *
 * It is deliberately not a general logger. One event kind, emitted from one
 * place — the bounded chokepoint — so the count means exactly one thing.
 */
export interface ExhaustionRecord {
  readonly attempts: number;
  readonly elapsedMs: number;
  readonly failureClass: string;
  readonly detail: string;
  readonly status: number | null;
}

export const EXHAUSTION_EVENT = "ctower:read-exhausted";

/** Bounded so a pathological loop cannot grow it without limit. */
const LIMIT = 50;
const records: ExhaustionRecord[] = [];
let counted = 0;

export function recordExhaustion(record: ExhaustionRecord): void {
  counted += 1;
  records.push(record);
  if (records.length > LIMIT) {
    records.shift();
  }
  if (typeof globalThis.dispatchEvent === "function") {
    globalThis.dispatchEvent(new CustomEvent(EXHAUSTION_EVENT, { detail: record }));
  }
}

/** How many bounded reads have exhausted in this page's lifetime. */
export function exhaustionCount(): number {
  return counted;
}

/** The most recent exhaustions, oldest first. */
export function exhaustionLog(): readonly ExhaustionRecord[] {
  return [...records];
}
