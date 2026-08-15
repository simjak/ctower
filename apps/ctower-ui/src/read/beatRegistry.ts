import { healthOf, registryOf } from "./sources/cadenceHealth";
import type { Beat, CadenceRegistry } from "./interface";

/**
 * The cadence registry as the record itself holds it.
 *
 * Heartbeats read the host's crontab and its own fire markers for as long as
 * ctower recorded no cadence of its own. `GET /v1/runtime/beat-routines` now
 * returns every registered revision with the server's own next fire, and
 * `GET /v1/runtime/beat-dispatches` returns the immutable effects each one has
 * emitted — which is the registry, the schedule and the fire history the screen
 * was already shaped for, from the instance instead of from the host it happens
 * to run on.
 *
 * Everything here is pure: the two payloads arrive parsed and this module folds
 * them. The requests stay in the one module that is allowed to make them.
 */

/** One registered routine, as the read parsed it. */
export interface BeatRoutineRead {
  readonly routineRef: string;
  readonly beatKey: string;
  readonly targetSession: string;
  readonly nextFireAt: string;
  /** Minutes of the hour the routine fires on. */
  readonly minutes: readonly number[];
  /** Hours of the day, or `null` for every hour. */
  readonly hours: readonly number[] | null;
  readonly timezone: string;
}

/** One emitted effect, as the read parsed it. */
export interface BeatDispatchRead {
  readonly routineRef: string;
  readonly emittedAt: string;
}

export const RECORD_HEALTH_RULE =
  "alive within 2 scheduled intervals of the last emitted dispatch · late to 5 · not arriving beyond · liveness unestablished while the record holds no dispatch for the routine";

const MINUTE_MS = 60_000;
const DAY_MINUTES = 1440;

/**
 * How long a beat may be silent before silence means something.
 *
 * A minute/hour set is not necessarily evenly spaced — `0,5 * * * *` fires twice
 * an hour with gaps of five minutes and fifty-five — so the interval that
 * decides lateness is the **largest** gap between consecutive scheduled fires,
 * wrapped across the day boundary. Taking the average or the smallest gap would
 * mark a beat late during a stretch it was never scheduled to fire in.
 */
export function scheduleIntervalMs(routine: BeatRoutineRead): number | null {
  const hours = routine.hours ?? [...Array.from({ length: 24 }).keys()];
  const fires = hours
    .flatMap((hour) => routine.minutes.map((minute) => hour * 60 + minute))
    .sort((left, right) => left - right);
  if (fires.length === 0) {
    return null;
  }
  if (fires.length === 1) {
    return DAY_MINUTES * MINUTE_MS;
  }
  let widest = (fires[0] ?? 0) + DAY_MINUTES - (fires.at(-1) ?? 0);
  for (let index = 1; index < fires.length; index += 1) {
    widest = Math.max(widest, (fires[index] ?? 0) - (fires[index - 1] ?? 0));
  }
  return widest * MINUTE_MS;
}

/** The schedule as the five-field expression an operator reads it in. */
export function scheduleText(routine: BeatRoutineRead): string {
  const minutes = routine.minutes.length === 0 ? "*" : routine.minutes.join(",");
  const hours = routine.hours === null ? "*" : routine.hours.join(",");
  return `${minutes} ${hours} * * * ${routine.timezone}`;
}

/** The newest dispatch each routine has emitted, keyed by its ref. */
function lastFires(dispatches: readonly BeatDispatchRead[]): ReadonlyMap<string, string> {
  const newest = new Map<string, string>();
  for (const dispatch of dispatches) {
    const held = newest.get(dispatch.routineRef);
    if (held === undefined || held < dispatch.emittedAt) {
      newest.set(dispatch.routineRef, dispatch.emittedAt);
    }
  }
  return newest;
}

function beatOf(routine: BeatRoutineRead, lastFire: string | undefined, now: number): Beat {
  const fired = lastFire ?? null;
  const { health, why } = healthOf(
    fired === null ? null : Date.parse(fired),
    scheduleIntervalMs(routine),
    now
  );
  return {
    seat: routine.targetSession,
    beat: routine.beatKey,
    schedule: scheduleText(routine),
    lastFire: fired,
    nextFire: routine.nextFireAt,
    health,
    why:
      fired === null
        ? `the record registers ${routine.routineRef} and holds no emitted dispatch for it`
        : why,
  };
}

/**
 * Fold the two record reads into the registry the screen renders.
 *
 * The four marks sum to the registered count by construction — `registryOf`
 * fails the read rather than shipping tiles that do not add up.
 */
export function recordCadenceRegistry(
  routines: readonly BeatRoutineRead[],
  dispatches: readonly BeatDispatchRead[],
  sourceLabel: string,
  observedAt: string
): CadenceRegistry {
  const newest = lastFires(dispatches);
  const now = Date.parse(observedAt);
  const beats = routines
    .map((routine) => beatOf(routine, newest.get(routine.routineRef), now))
    .sort((left, right) => left.beat.localeCompare(right.beat));
  return registryOf(beats, sourceLabel, observedAt, RECORD_HEALTH_RULE);
}
