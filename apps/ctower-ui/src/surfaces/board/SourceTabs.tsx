"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import type { ReactElement } from "react";
import { boardHref } from "./boardHref";
import type { BoardSelection } from "./boardHref";
import { Count } from "@/surfaces/Count";

export interface SourceTab {
  readonly key: string;
  readonly label: string;
  readonly count: number;
}

/**
 * The board's secondary filter. Project is the primary axis above; this filters
 * its cards by the independent recorded `source.kind` provenance dimension.
 *
 * The selection lives in the URL, so the tab counts, the lane tally and the
 * list itself are all computed on the server from the same choice and cannot
 * disagree with the rows on screen.
 */
export function SourceTabs({
  tabs,
  selected,
  selection,
}: {
  readonly tabs: readonly SourceTab[];
  readonly selected: string;
  /** Everything else the screen is narrowed to, so this control carries it. */
  readonly selection: BoardSelection;
}): ReactElement {
  const router = useRouter();
  const choose = useCallback(
    (key: string): void => {
      router.push(boardHref({ ...selection, source: key }));
    },
    [router, selection]
  );

  return (
    <nav
      className="tabs"
      aria-label="Filter by recorded source"
      style={{ flexWrap: "wrap", rowGap: "8px" }}
    >
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
          {/* the same `.tab .n` pill the Inbox uses, and it means something else
              there — so it says what it counts here too (#239) */}
          {tab.label}{" "}
          <Count
            value={tab.count}
            unit={tab.count === 1 ? "card" : "cards"}
            detail={`${tab.count.toString()} cards on the board from this source`}
          />
        </label>
      ))}
    </nav>
  );
}
