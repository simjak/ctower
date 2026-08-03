import type { ReactElement } from "react";

/**
 * A number this surface prints in the vendored `.n` pill, with what it counts.
 *
 * Round-3 QA (#239) found the same pill meaning *unread* on the Inbox and
 * *cards* on the Board, both as bare numbers, with the disambiguation only in a
 * native `title`. The two even disagreed for one seat in one viewport:
 * `ctower-commander 442` sat directly above `25 of 444 shown`. The seat holding
 * the most mail on the box — 485 messages, all read — rendered as a bare `0`,
 * which reads as an empty inbox rather than a fully-read one.
 *
 * This is the only place the pill is written. A count therefore cannot reach a
 * screen without the unit it counts in, and
 * `tests/repository/test_surface_affordances.py` fails closed on a `className="n"`
 * written anywhere else.
 */
export function Count({
  value,
  unit,
  detail,
}: {
  readonly value: number;
  /** What the number counts, in operator language: `unread`, `cards`, `held`. */
  readonly unit: string;
  /** The fuller reading, for the hover — never the only place the unit exists. */
  readonly detail?: string | undefined;
}): ReactElement {
  return (
    <span className="n" title={detail}>
      {value}
      <span style={{ marginLeft: "3px", opacity: 0.75 }}>{unit}</span>
    </span>
  );
}
