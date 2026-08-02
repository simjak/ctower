"use client";

import { useState } from "react";
import type { ReactElement, ReactNode } from "react";

/**
 * The File / Diff switch. Like the feed's Chat / Raw switch it chooses a
 * reading, never a write, so it stays live in read-only v1.
 */
export function FileDiffSwitch({
  file,
  diff,
}: {
  readonly file: ReactNode;
  readonly diff: ReactNode;
}): ReactElement {
  const [view, setView] = useState<"file" | "diff">("file");
  return (
    <>
      <div className="pane-head">
        <span className="path">—</span>
        <span className="spacer" />
        <span className="seg">
          <label>
            <input
              type="radio"
              name="xview"
              checked={view === "file"}
              onChange={() => {
                setView("file");
              }}
            />
            File
          </label>
          <label>
            <input
              type="radio"
              name="xview"
              checked={view === "diff"}
              onChange={() => {
                setView("diff");
              }}
            />
            Diff
          </label>
        </span>
      </div>
      <div data-view="file" hidden={view !== "file"}>
        {file}
      </div>
      <div data-view="diff" hidden={view !== "diff"}>
        {diff}
      </div>
    </>
  );
}
