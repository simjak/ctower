"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import type { ReactElement } from "react";
import { ALL_SOURCES } from "./lanes";

export interface SourceTab {
  readonly key: string;
  readonly label: string;
  readonly count: number;
}

/**
 * The board filter. The record carries no project fact yet — project scoping
 * is #185 / D29 — so the dimension this filters on is `source.kind`, which the
 * record does carry and which `/v1/board` accepts as a query filter.
 *
 * The selection lives in the URL, so the counts, the column counts and the
 * empty columns are all computed on the server from the same choice and cannot
 * disagree with the rows on screen.
 */
export function SourceTabs({
  tabs,
  selected,
}: {
  readonly tabs: readonly SourceTab[];
  readonly selected: string;
}): ReactElement {
  const router = useRouter();
  const choose = useCallback(
    (key: string): void => {
      router.push(key === ALL_SOURCES ? "/board" : `/board?source=${encodeURIComponent(key)}`);
    },
    [router]
  );

  return (
    <nav className="tabs" aria-label="Filter by recorded source">
      {tabs.map((tab) => (
        <label className="tab" key={tab.key}>
          <input
            type="radio"
            name="source"
            value={tab.key}
            checked={tab.key === selected}
            onChange={() => {
              choose(tab.key);
            }}
          />
          {tab.label} <span className="n">{tab.count}</span>
        </label>
      ))}
    </nav>
  );
}
