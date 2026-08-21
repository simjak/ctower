import type { ReactElement, ReactNode } from "react";
import type { PoolEntry } from "@/read/interface";

/**
 * The three axes of one credential-pool account, drawn as the accepted
 * design's triad instead of as six words.
 *
 * `docs/internal/design/operator-cockpit.html` states the rule that makes a
 * glyph legal here: **a glyph may stand for one axis, never for a composed
 * verdict.** Three glyphs in a fixed order — a key, a gauge, a signal — take
 * `auth`, `quota` and `reach` out of the ink without merging anything. Three
 * marks stay three marks, each keeping the record's own word beside it and its
 * own tone, so a cleared axis recedes and a blocking one is where the eye
 * lands.
 *
 * These are **not** the six marks `ctowerctl` prints. `StateGlyph` owns those,
 * they are shared vocabulary with the CLI, and they change in both places or
 * neither. The axis glyphs are a second, disjoint set that names an axis rather
 * than a state, and the two never stand in for each other.
 *
 * The axis name stays in the document on every chip. A glyph only a sighted
 * reader can name is a label that failed, so the word is screen-reader text
 * rather than deleted text.
 */

export type AxisKey = "auth" | "quota" | "reach";

/** auth is a key, quota is a gauge, reach is a signal — the mockup's own paths. */
const AXIS_GLYPH: Readonly<Record<AxisKey, ReactNode>> = {
  auth: (
    <>
      <circle cx="5.8" cy="8" r="2.4" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8.2 8h5M11.4 8v2.3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </>
  ),
  quota: (
    <>
      <path d="M3.2 11.4a5 5 0 0 1 9.6 0" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 11.4l2.7-3.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </>
  ),
  reach: (
    <>
      <rect x="3" y="10" width="2" height="3.2" rx=".6" fill="currentColor" />
      <rect x="7" y="7.4" width="2" height="5.8" rx=".6" fill="currentColor" />
      <rect x="11" y="4.6" width="2" height="8.6" rx=".6" fill="currentColor" />
    </>
  ),
};

/**
 * How each recorded word reads, in the tones the accepted design assigns.
 *
 * The two that matter most are the two the design refuses to let look alike:
 * `capped` takes the warn hue — the account passed login and is waiting on a
 * clock — and a dead lineage takes the refusal hue, because login itself is
 * gone. Collapsing that pair costs the operator the next action, so they are
 * separated here at the tone as well as at the word.
 *
 * `unknown` is neither. It carries the neutral chip **and a dashed border**,
 * because D1 forbids an unobserved axis resolving to the settled grey of an
 * observed one, and the dash is the half of that distinction that survives
 * greyscale.
 */
const TONE: Readonly<Record<string, string>> = {
  healthy: "v-pass",
  "lineage-dead": "v-held",
  "chain-burned": "v-held",
  available: "v-pass",
  capped: "v-changes",
  unfunded: "v-changes",
  ok: "v-pass",
  "edge-challenged": "v-changes",
  enrolled: "v-filed",
  discovered: "v-changes",
  unknown: "v-filed limits-unobserved",
};

export function toneOf(state: string): string {
  return TONE[state] ?? "v-filed";
}

/** One axis: its glyph, its name for a reader who cannot see one, its word. */
export function AxisChip({
  axis,
  state,
}: {
  readonly axis: AxisKey;
  readonly state: string;
}): ReactElement {
  return (
    <span className={`verdict limits-axis ${toneOf(state)}`}>
      <svg className="limits-axis-ic" viewBox="0 0 16 16" fill="none" aria-hidden>
        {AXIS_GLYPH[axis]}
      </svg>
      <span className="limits-axis-name">{axis}</span>
      {state}
    </span>
  );
}

/** The triad's fixed order, declared once so no screen can reorder it. */
export const AXES = ["auth", "quota", "reach"] as const;

const CLEAR: Readonly<Record<AxisKey, string>> = {
  auth: "healthy",
  quota: "available",
  reach: "ok",
};

const CLOSE: Readonly<Record<string, string>> = {
  capped: "wait for the provider to reset it",
  "lineage-dead": "sign in again, on the host",
  "chain-burned": "sign in again, on the host",
};

export interface Blocking {
  /** The axes the record's own words leave unclear, in the triad's order. */
  readonly axes: readonly AxisKey[];
  /** What closes them, where the meanings table answers; `null` where it does not. */
  readonly close: string | null;
}

export function statedAxes(entry: PoolEntry): Readonly<Record<AxisKey, string>> {
  return { auth: entry.authState, quota: entry.quotaState, reach: entry.reachState };
}

/**
 * Which of the three axes is not clear, and what closes it.
 *
 * `AC-HAD-10` is the source of both halves. An entry is selectable only when
 * all three axes are clear, so naming the ones that are not is naming which of
 * the three chips already on the row is not clear — not composing a fourth
 * state out of them. The closes are the pool's own meanings table and stop
 * where it stops: a state the table does not answer for gets no line, because
 * an invented next action is worse than an absent one.
 */
export function blockingOf(entry: PoolEntry): Blocking {
  const stated = statedAxes(entry);
  const axes = AXES.filter((axis) => stated[axis] !== CLEAR[axis]);
  const closes: string[] = [];
  for (const axis of axes) {
    const close = CLOSE[stated[axis]];
    if (close !== undefined && !closes.includes(close)) {
      closes.push(close);
    }
  }
  return { axes, close: closes.length === 0 ? null : closes.join(" · ") };
}
