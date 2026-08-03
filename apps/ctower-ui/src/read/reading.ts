import type { Reading } from "./interface";

/**
 * Derivation over a reading.
 *
 * A screen that needs a value *computed* from a read still must not collapse
 * the read's state. `mapReading` carries `absent` and `unavailable` through
 * untouched and only runs the projection on a present value, so a derived view
 * of an unreachable source stays unreachable rather than becoming empty.
 */
export function mapReading<A, B>(
  reading: Reading<A>,
  project: (value: A) => Reading<B>
): Reading<B> {
  switch (reading.state) {
    case "present":
      return project(reading.value);
    case "absent":
      return reading;
    case "unavailable":
      return reading;
  }
}

/** True only for a read that reached its source and found nothing to show. */
export function isAbsent<T>(reading: Reading<T>): boolean {
  return reading.state === "absent";
}

/** True only for a read that did not reach its source. */
export function isUnreached<T>(reading: Reading<T>): boolean {
  return reading.state === "unavailable";
}
