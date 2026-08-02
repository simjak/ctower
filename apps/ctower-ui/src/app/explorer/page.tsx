import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";
import { DeclaredState } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter } from "@/read/adapter";
import { FileDiffSwitch } from "@/surfaces/explorer/FileDiffSwitch";

export const dynamic = "force-dynamic";

export default async function ExplorerPage(): Promise<ReactElement> {
  const worktree = await recordAdapter.sessionWorktree();
  return (
    <>
      <Chrome section="Explorer" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Explorer</h1>
            <p>
              The session&rsquo;s own worktree, as it stands right now — and what it has actually
              changed against main. A branch that claims work exists is not the same as a diff that
              shows it.
            </p>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <div className="ed">
              <div className="tree">
                <div className="dir">
                  <span className="cw">⌄</span>no worktree recorded
                </div>
                <div className="leaf">files · counts · diff against main</div>
              </div>
              <div className="pane">
                <FileDiffSwitch
                  file={<DeclaredState reading={worktree} />}
                  diff={<DeclaredState reading={worktree} />}
                />
              </div>
            </div>
          </section>

          <RecordFoot />
        </div>
      </main>
    </>
  );
}
