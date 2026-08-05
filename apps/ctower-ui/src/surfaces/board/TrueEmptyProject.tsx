import type { ReactElement } from "react";
import { StateGlyph } from "@/frame/StateGlyph";

/**
 * The named block for a true-empty project — the second way a board can answer
 * watermark 0 of 0 with zero cards.
 *
 * The record answered <span class="mono">0 of 0</span> for THIS project while
 * the portfolio (the unscoped board) holds a nonzero watermark. That is not an
 * outage and not a fresh instance: the instance plainly holds records, so
 * `project` simply has not been imported yet — its import chain has not run.
 * This block says so in the operator's words and points at the portfolio view,
 * where every imported card is visible, so an un-imported project can never be
 * mistaken for an empty portfolio (and never renders blank).
 *
 * This is NOT the restart/fresh refusal: when the portfolio is ALSO at 0 the
 * surface renders `ZeroOfZeroRefusal`, never this. The decision lives in
 * `read/boardProjection.ts` (`boardEmptyKind`); this component is the one place
 * its "true-empty-project" verdict is rendered.
 */
export function TrueEmptyProject({ project }: { readonly project: string }): ReactElement {
  return (
    <main className="page">
      <div className="wrap" style={{ paddingTop: "16px" }}>
        <div className="slots" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
          <div
            className="slot"
            style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)" }}
          >
            <StateGlyph name="attn" />
            <div className="e">
              <div className="k">project {project} carries no imported cards yet</div>
              <div className="d">
                The record answered <span className="mono">watermark 0 of 0</span> for {project}{" "}
                while the portfolio holds a nonzero watermark — so this is not an outage and not an
                empty portfolio. {project}&rsquo;s import chain has not run yet; the import fills
                this project&rsquo;s board. Every imported card across projects is visible in the
                portfolio view, linked below.
              </div>
              <div className="f">
                <a href="/board">the portfolio view (all cards)</a>
                <span>read with project_key={project}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
