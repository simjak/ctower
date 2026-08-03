"use client";

import { useState } from "react";
import type { ReactElement, ReactNode } from "react";

/**
 * The Chat / Raw terminal switch. Both views render the same recorded events,
 * so they cannot disagree; the switch only chooses which reading of them is on
 * screen. It is a view control, not a command, and stays live in read-only v1.
 */
export function FeedViews({
  sessionMeta,
  chat,
  raw,
}: {
  readonly sessionMeta: ReactNode;
  readonly chat: ReactNode;
  readonly raw: ReactNode;
}): ReactElement {
  const [view, setView] = useState<"chat" | "raw">("chat");
  return (
    <>
      <div className="sess">
        {sessionMeta}
        <span className="spacer" />
        <span className="seg">
          <label>
            <input
              type="radio"
              name="fview"
              checked={view === "chat"}
              onChange={() => {
                setView("chat");
              }}
            />
            Chat
          </label>
          <label>
            <input
              type="radio"
              name="fview"
              checked={view === "raw"}
              onChange={() => {
                setView("raw");
              }}
            />
            Raw terminal
          </label>
        </span>
      </div>
      <div data-fview="chat" hidden={view !== "chat"}>
        {chat}
      </div>
      <div data-fview="raw" hidden={view !== "raw"}>
        {raw}
      </div>
    </>
  );
}
