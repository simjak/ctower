import type { Beat, BeatHealth, CadenceRegistry } from "../interface";

/**
 * The one health rule both cadence sources use.
 *
 * Health is derived, and the derivation is stated on the screen rather than
 * implied: a beat is alive while its last fire is inside two of its own
 * intervals, late out to five, and not arriving beyond that. A beat whose last
 * fire cannot be established is `unknown` — never "alive", and never "dead".
 */
export const HEALTH_RULE =
  "alive within 2 intervals of the last fire · late to 5 · not arriving beyond · unknown when no last fire is recorded";

export function healthOf(
  lastFireMs: number | null,
  intervalMs: number | null,
  now: number
): { readonly health: BeatHealth; readonly why: string | null } {
  if (lastFireMs === null || intervalMs === null || intervalMs <= 0) {
    return { health: "unknown", why: "no last fire is recorded for this beat" };
  }
  const missed = Math.floor((now - lastFireMs) / intervalMs);
  if (missed <= 2) {
    return { health: "alive", why: null };
  }
  const text = `${missed.toString()} intervals since the last fire`;
  return missed <= 5 ? { health: "late", why: text } : { health: "dead", why: text };
}

export function registryOf(
  beats: readonly Beat[],
  sourceLabel: string,
  sweptAt: string,
  healthRule: string
): CadenceRegistry {
  const count = (health: BeatHealth): number =>
    beats.filter((beat) => beat.health === health).length;
  return {
    beats,
    healthRule,
    registered: beats.length,
    arriving: count("alive"),
    late: count("late"),
    notArriving: count("dead"),
    sourceLabel,
    sweptAt,
  };
}
