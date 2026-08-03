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
  "alive within 2 intervals of the last fire · late to 5 · not arriving beyond · liveness unestablished when no fire marker this source reads has ever been written, which is a registry gap rather than a verdict on the beat";

export function healthOf(
  lastFireMs: number | null,
  intervalMs: number | null,
  now: number
): { readonly health: BeatHealth; readonly why: string | null } {
  if (lastFireMs === null) {
    return { health: "unknown", why: "no last fire is recorded for this beat" };
  }
  if (intervalMs === null || intervalMs <= 0) {
    // the fire is known and the schedule is not periodic, so lateness has no
    // meaning here — which is a different sentence from "it never fired"
    return {
      health: "unknown",
      why: "this schedule states no repeating interval, so a missed fire cannot be counted",
    };
  }
  const missed = Math.floor((now - lastFireMs) / intervalMs);
  if (missed <= 2) {
    return { health: "alive", why: null };
  }
  const text = `${missed.toString()} intervals since the last fire`;
  return missed <= 5 ? { health: "late", why: text } : { health: "dead", why: text };
}

/**
 * The registry, with every beat counted in exactly one tile.
 *
 * Round-3 QA (#238) found the four tiles reading 5 · 4 · 0 · 0: the fifth beat
 * sat in `unknown`, which no tile counted, so the operator had to notice a beat
 * was unaccounted for by doing the arithmetic. The four marks now sum to the
 * registered count by construction, and the assertion below fails the read
 * rather than shipping a set of tiles that does not add up.
 */
export function registryOf(
  beats: readonly Beat[],
  sourceLabel: string,
  sweptAt: string,
  healthRule: string
): CadenceRegistry {
  const count = (health: BeatHealth): number =>
    beats.filter((beat) => beat.health === health).length;
  const registry: CadenceRegistry = {
    beats,
    healthRule,
    registered: beats.length,
    arriving: count("alive"),
    late: count("late"),
    notArriving: count("dead"),
    unaccounted: count("unknown"),
    sourceLabel,
    sweptAt,
  };
  const marked = registry.arriving + registry.late + registry.notArriving + registry.unaccounted;
  if (marked !== registry.registered) {
    throw new Error(
      `the cadence tiles count ${marked.toString()} of ${registry.registered.toString()} registered beats; a beat in no tile is a beat nobody is watching`
    );
  }
  return registry;
}
