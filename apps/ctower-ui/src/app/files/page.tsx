import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";
import { DeclaredState } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { INERT_CONTROL } from "@/frame/inert";
import { recordAdapter } from "@/read/adapter";

export const dynamic = "force-dynamic";

export default async function FilesPage(): Promise<ReactElement> {
  const files = await recordAdapter.authoredFiles();
  return (
    <>
      <Chrome section="Files" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Files</h1>
            <p>
              Souls, skills, harness guides, project rules and repo files, edited in the surface
              that runs them. There is no quiet write path: saving opens a branch and a pull
              request, and the same review and CSO gates that hold for code hold for a soul.
            </p>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <div className="ed">
              <div className="tree">
                <div className="dir">
                  <span className="cw">⌄</span>no tree recorded
                </div>
                <div className="leaf">souls · skills · guides · project rules</div>
              </div>
              <div className="pane">
                <div className="pane-head">
                  <span className="path">—</span>
                  <span className="spacer" />
                  <span className="meta">nothing open</span>
                </div>
                <DeclaredState reading={files} />
                <div className="gate-note show">
                  a save would open a branch off main, one commit, and a pull request against
                  protected main · requires: review sign-off (cross-family) · nothing is written
                  until that pull request merges — and read-only v1 opens none of it
                </div>
                <div className="editor-foot">
                  <button className="btn" type="button" disabled style={INERT_CONTROL}>
                    Save — commit via review
                  </button>
                  <button className="btn ghost" type="button" disabled style={INERT_CONTROL}>
                    Revert
                  </button>
                  <span className="note">
                    Read-only v1: this surface holds no authority to write, so both controls are
                    inert by design. Direct writes to main are refused by name in every path.
                  </span>
                </div>
              </div>
            </div>
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Recent commits</h2>
              <span className="sub">this path</span>
            </header>
            <DeclaredState reading={files} />
          </section>

          <RecordFoot />
        </div>
      </main>
    </>
  );
}
