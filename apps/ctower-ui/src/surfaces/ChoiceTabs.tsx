"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import type { ReactElement } from "react";

export interface Choice {
  /** The value written to the URL. */
  readonly key: string;
  /** What the reader sees; may be shorter than the key. */
  readonly label: string;
  /** Omitted entirely when the source carries no count — never rendered as 0. */
  readonly count?: number;
  readonly title?: string;
}

/**
 * The one selector idiom this product has.
 *
 * The choice lives in the URL, so everything the selection drives — counts,
 * rows, the addressing line, the pane — is rendered on the server from the same
 * value and cannot disagree with itself. A tab shows a count only when its
 * source has one: a `0` beside a crew that has no unread concept would be a
 * number this surface invented.
 */
export function ChoiceTabs({
  choices,
  selected,
  route,
  parameter = "seat",
  label,
}: {
  readonly choices: readonly Choice[];
  readonly selected: string;
  readonly route: string;
  readonly parameter?: string;
  readonly label: string;
}): ReactElement {
  const router = useRouter();
  const choose = useCallback(
    (key: string): void => {
      router.push(`${route}?${parameter}=${encodeURIComponent(key)}`);
    },
    [parameter, route, router]
  );

  return (
    <nav
      className="tabs"
      aria-label={label}
      style={{ paddingLeft: 0, paddingRight: 0, paddingTop: "16px" }}
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
          {choice.count === undefined ? null : <span className="n">{choice.count}</span>}
        </label>
      ))}
    </nav>
  );
}
