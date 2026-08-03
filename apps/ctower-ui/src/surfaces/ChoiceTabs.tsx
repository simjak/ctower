"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import type { ReactElement } from "react";
import { Count } from "./Count";

/**
 * A number on a tab, and what it counts.
 *
 * The unit is not optional. Round-3 QA (#239) found the Inbox tabs counting
 * *unread* and the panel beside them counting *total*, both as bare numbers a
 * few pixels apart, with the disambiguation only in a `title` — invisible on the
 * screen, absent on touch, unreachable by keyboard. The seat with the most mail
 * on the box, 485 messages all read, rendered as a bare `0`. The same component
 * on Board means total. One component, two meanings, no label on either.
 *
 * Pairing the number with its unit in the type makes an unlabelled count
 * unrepresentable rather than merely discouraged.
 */
export interface TabCount {
  readonly value: number;
  /** What the number counts, in operator language: `unread`, `cards`. */
  readonly unit: string;
  /** The fuller reading, for the hover — never the only place the unit exists. */
  readonly detail?: string | undefined;
}

export interface Choice {
  /** The value written to the URL. */
  readonly key: string;
  /** What the reader sees; may be shorter than the key. */
  readonly label: string;
  /** Omitted entirely when the source carries no count — never rendered as 0. */
  readonly count?: TabCount;
  readonly title?: string;
}

/**
 * The one selector idiom this product has.
 *
 * The choice lives in the URL, so everything the selection drives — counts,
 * rows, the addressing line, the pane — is rendered on the server from the same
 * value and cannot disagree with itself. A tab shows a count only when its
 * source has one: a `0` beside a crew that has no unread concept would be a
 * number this surface invented — and every count it does show carries the unit
 * it counts in, beside the number rather than behind a hover.
 */
export function ChoiceTabs({
  choices,
  selected,
  route,
  parameter = "seat",
  label,
  keeping = {},
}: {
  readonly choices: readonly Choice[];
  readonly selected: string;
  readonly route: string;
  readonly parameter?: string;
  readonly label: string;
  /**
   * Other selections this screen holds, carried through unchanged. A screen
   * with two filters must not silently drop one when the other is used.
   */
  readonly keeping?: Readonly<Record<string, string>>;
}): ReactElement {
  const router = useRouter();
  const choose = useCallback(
    (key: string): void => {
      const query = new URLSearchParams(keeping);
      if (key === "") {
        query.delete(parameter);
      } else {
        query.set(parameter, key);
      }
      const search = query.toString();
      router.push(search === "" ? route : `${route}?${search}`);
    },
    [keeping, parameter, route, router]
  );

  return (
    <nav
      className="tabs"
      aria-label={label}
      // the row wraps rather than clipping: at 1440px the eighth Inbox tab sat
      // under the right edge, and it was the `0` that most needed reading (#239)
      style={{
        paddingLeft: 0,
        paddingRight: 0,
        paddingTop: "16px",
        flexWrap: "wrap",
        rowGap: "8px",
      }}
    >
      {choices.map((choice) => (
        <label className="tab" key={choice.key} title={choice.title ?? choice.key}>
          <input
            type="radio"
            name={parameter}
            value={choice.key}
            checked={choice.key === selected}
            onChange={() => {
              choose(choice.key);
            }}
          />
          {choice.label}
          {choice.count === undefined ? null : (
            <Count
              value={choice.count.value}
              unit={choice.count.unit}
              detail={choice.count.detail}
            />
          )}
        </label>
      ))}
    </nav>
  );
}
