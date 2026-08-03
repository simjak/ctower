import type { ReactElement } from "react";
import { StateGlyph } from "@/frame/StateGlyph";
import { clockText, spanBetween } from "@/read/elapsed";
import type { StageEntry } from "@/surfaces/record/events";

function subText(entry: StageEntry): string {
  if (entry.leftAt === null) {
    return `entered ${clockText(entry.enteredAt)}`;
  }
  const span = spanBetween(entry.enteredAt, entry.leftAt);
  return span === null ? clockText(entry.enteredAt) : `${clockText(entry.enteredAt)} · ${span}`;
}

/**
 * The stage strip, built from the ticket's own `workflow.changed` events. It
 * shows the stages the workflow entered — not a stage vocabulary this instance
 * does not run, and not a stage a ticket never reached.
 */
export function StageStrip({ stages }: { readonly stages: readonly StageEntry[] }): ReactElement {
  const last = stages.length - 1;
  return (
    <nav className="strip" aria-label="Recorded stages">
      {stages.map((entry, index) => {
        const closed = entry.lifecycleFacts.includes("closed");
        const current = index === last && !closed;
        return (
          <div
            className={`st ${current ? "now" : "done"}`}
            key={`${entry.stage}-${entry.enteredAt}`}
          >
            <div className="nm">
              <StateGlyph name={current ? "flight" : "done"} />
              {entry.stage}
            </div>
            <div className="sub">{subText(entry)}</div>
          </div>
        );
      })}
    </nav>
  );
}
