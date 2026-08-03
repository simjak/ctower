import type { ReactElement } from "react";
import { StateGlyph } from "@/frame/StateGlyph";
import type { UnresolvedSources } from "@/read/boardProjection";

/**
 * The board's own honesty line about its filter.
 *
 * Each card's source comes from a second read. When some of those reads do not
 * answer, the filter counts below are computed over fewer cards than the board
 * shows — so the board says exactly how many, and why, instead of letting the
 * counts quietly disagree with the rail.
 */
export function UnreadSources({
  unresolved,
}: {
  readonly unresolved: UnresolvedSources;
}): ReactElement | null {
  if (unresolved.count === 0) {
    return null;
  }
  return (
    <div className="page" style={{ paddingBottom: 0 }}>
      <div className="wrap">
        <div
          className="slots"
          style={{ gridTemplateColumns: "minmax(0, 1fr)", padding: "16px 0 0" }}
        >
          <div
            className="slot"
            style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)" }}
          >
            <StateGlyph name="attn" />
            <div className="e">
              <div className="k">
                {unresolved.count.toString()} of these cards could not be joined to their ticket
                read
              </div>
              <div className="d">
                Their source is unknown rather than unrecorded, so they are not counted in the
                source filter above and are marked <b>not reached</b> on the card. The lanes,
                titles, priorities and custodians below still come from the board read, which did
                answer.
              </div>
              <div className="f" style={{ overflowWrap: "anywhere" }}>
                <span className="req">
                  {unresolved.unreached.toString()} unreached after their bounded retries
                </span>
                {unresolved.reason === null ? null : <span>{unresolved.reason}</span>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
