import type { ReactElement } from "react";
import { StateGlyph } from "@/frame/StateGlyph";
import { landsText, NO_PROJECT_SCOPE } from "@/read/futureSources";
import type { BoardScope } from "@/read/interface";

/**
 * What the reader is actually looking at when a project tab is selected.
 *
 * The read *is* scoped — `project_key` is a required parameter and this surface
 * sends the selected project. But the cards that come back carry no project
 * member, so nothing on the board can be attributed to a project, and three tabs
 * over one unattributed set would tell the operator that manibo holds tickets it
 * does not hold. That is the same failure as a green number that means nothing:
 * a distinction drawn on the screen that the record does not make.
 *
 * So the tab exists — the axis is the operator's, and it is the right one — and
 * this block says plainly that the set below is the portfolio's until the record
 * carries a project fact. It disappears on its own the moment it does:
 * `scope.cardsCarryProject` is derived from the card the adapter parses, not
 * from a probe, so the sentence cannot outlive the condition it describes.
 */
export function ScopeNote({ scope }: { readonly scope: BoardScope }): ReactElement | null {
  if (scope.cardsCarryProject) {
    return null;
  }
  return (
    <div className="wrap" style={{ paddingTop: "16px" }}>
      <div className="slots" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
        <div
          className="slot"
          style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)" }}
        >
          <StateGlyph name="attn" />
          <div className="e">
            <div className="k">these are not {scope.projectKey}&rsquo;s tickets</div>
            <div className="d">
              This board was read with <span className="mono">project_key={scope.projectKey}</span>,
              and the record answered — but a Board card carries no project of its own, so no ticket
              below can be attributed to {scope.projectKey} or to any other project. What you are
              reading is the portfolio: the same set every project tab shows. The tab is here
              because the axis is right; the split is not something this surface may invent.
            </div>
            <div className="f">
              <span className="req" title={NO_PROJECT_SCOPE.why ?? undefined}>
                a project fact on a ticket {landsText(NO_PROJECT_SCOPE)}
              </span>
              <span>read-only v1</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
