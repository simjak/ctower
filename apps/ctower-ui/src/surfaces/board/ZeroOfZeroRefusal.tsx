import type { ReactElement } from "react";
import { StateGlyph } from "@/frame/StateGlyph";
import type { BoardSnapshot } from "@/read/interface";

/**
 * The named block for the restart/fresh board answer — one of the two ways a
 * board can answer watermark 0 of 0 with zero cards.
 *
 * When the board's own watermark AND the portfolio's are both 0 (or the
 * portfolio read did not answer), this draws in the board body's place: the
 * signature is an instance that just restarted, is mid-rebuild, or is genuinely
 * fresh, and an empty answer rendered as truth is how a real outage hides work.
 * It states that possibility and the fresh-instance possibility, names the
 * watermark it refused, and points at the reload that re-checks the instance.
 *
 * This is NOT the true-empty-project block: a project whose import has not run
 * while the portfolio holds records renders `TrueEmptyProject`, never this.
 * The decision lives in `read/boardProjection.ts` (`boardEmptyKind`); this
 * component is the one place its "restart-fresh" verdict is rendered.
 */
export function ZeroOfZeroRefusal({
  project,
  snapshot,
}: {
  readonly project: string;
  readonly snapshot: BoardSnapshot;
}): ReactElement {
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
              <div className="k">
                refusing to render {project} as empty — the record answered watermark 0 of 0
              </div>
              <div className="d">
                The record answered <span className="mono">watermark 0 of 0</span> with zero cards,
                and the portfolio answered the same, and this surface is refusing to render that
                answer as an empty portfolio. Either the API is restarting or rebuilding its
                projection, or this is a fresh instance with nothing recorded yet — neither is proof
                the portfolio is empty. An empty answer rendered as truth is how a real outage hides
                work (the honesty class this surface guards, one level deeper: during the runtime
                swap on 2026-08-04 this board said &ldquo;0 of 0&rdquo; while cards sat safe at a
                higher watermark).
              </div>
              <div className="f">
                <span className="req">
                  reload to re-check — the moment the instance answers a nonzero watermark, this
                  board renders normally
                </span>
                <a href={`/board?project=${encodeURIComponent(project)}`}>reload now</a>
                <span>
                  projection {snapshot.health.toLowerCase()} · watermark{" "}
                  {snapshot.projectionWatermark.toString()} of {snapshot.sourceWatermark.toString()}{" "}
                  · read with project_key=
                  {snapshot.scope.projectKey}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
