import type { ReactElement } from "react";
import { StateGlyph } from "./StateGlyph";
import type { Ranked } from "@/read/selectors";

/**
 * A ranking made from an incomplete fan-out, said out loud.
 *
 * When a selector ranked candidates and some of them did not answer, the winner
 * may not be the true winner. That is not a failure — the screen still has
 * something real to show — but it is not the confident claim the surface would
 * otherwise be making, so it is stated where the claim is made rather than
 * left for a reader to discover.
 */
export function Provisional<T>({ ranked }: { readonly ranked: Ranked<T> }): ReactElement | null {
  if (ranked.unread === 0) {
    return null;
  }
  return (
    <div className="slots" style={{ gridTemplateColumns: "minmax(0, 1fr)", paddingBottom: 0 }}>
      <div
        className="slot"
        style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)" }}
      >
        <StateGlyph name="attn" />
        <div className="e">
          <div className="k">this choice is provisional</div>
          <div className="d">
            {ranked.unread.toString()} of {ranked.considered.toString()} candidates did not answer,
            so the one shown may not be the most recent. It is the most recent of those that did.
          </div>
          {ranked.reason === null ? null : (
            <div className="f" style={{ overflowWrap: "anywhere" }}>
              <span className="req">{ranked.reason}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
