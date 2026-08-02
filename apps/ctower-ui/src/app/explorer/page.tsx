import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import type { SessionWorktree } from "@/read/interface";
import { FileDiffSwitch } from "@/surfaces/explorer/FileDiffSwitch";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Explorer</h1>
      <p>
        The session&rsquo;s own worktree, as it stands right now — and what it has actually changed
        against main. A branch that claims work exists is not the same as a diff that shows it.
      </p>
    </div>
  );
}

function Changed({ worktree }: { readonly worktree: SessionWorktree }): ReactElement {
  return (
    <div className="tree">
      <div className="dir">
        <span className="cw">⌄</span>
        {worktree.branch ?? "detached"} vs {worktree.base}
      </div>
      {worktree.files.length === 0 ? (
        <div className="leaf">no file differs from {worktree.base}</div>
      ) : (
        worktree.files.map((file) => (
          <div className="leaf" key={file.path} style={{ paddingLeft: "24px" }}>
            {file.path}
            <span className="fstat m">
              {file.added === null ? "bin" : `+${file.added.toString()}`}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

function ExplorerBody({ worktree }: { readonly worktree: SessionWorktree }): ReactElement {
  const added = worktree.files.reduce((total, file) => total + (file.added ?? 0), 0);
  const removed = worktree.files.reduce((total, file) => total + (file.removed ?? 0), 0);
  return (
    <>
      <Chrome section="Explorer" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <ChoiceTabs
            label="Choose a worktree"
            route="/explorer"
            selected={worktree.root}
            choices={worktree.worktrees.map((path) => ({
              key: path,
              label: path.split("/").at(-1) ?? path,
              title: path,
            }))}
          />

          <section className="panel" style={{ marginTop: "16px" }}>
            <div className="ed">
              <Changed worktree={worktree} />
              <div className="pane">
                <FileDiffSwitch
                  path={worktree.root}
                  file={
                    <div className="pane-head" style={{ borderTop: 0 }}>
                      <span className="meta">{worktree.files.length.toString()} files changed</span>
                      <span className="meta" style={{ color: "var(--proven-deep)" }}>
                        +{added.toString()}
                      </span>
                      <span className="meta" style={{ color: "var(--refuse-deep)" }}>
                        −{removed.toString()}
                      </span>
                      <span className="spacer" />
                      <span className="meta">
                        {worktree.branch ?? "detached"} @ {worktree.head ?? "—"} vs {worktree.base}
                      </span>
                    </div>
                  }
                  diff={
                    <div className="diff">
                      {worktree.diff.map((line, index) => (
                        <span
                          className={line.kind === "context" ? "dl" : `dl ${line.kind}`}
                          key={`${index.toString()}:${line.text}`}
                        >
                          {line.text}
                        </span>
                      ))}
                      {worktree.truncated ? (
                        <span className="dl hunk">
                          … diff truncated at this surface&rsquo;s line cap; the branch carries more
                        </span>
                      ) : null}
                    </div>
                  }
                />
              </div>
            </div>
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.explorer}
            watermark={`${worktree.worktrees.length.toString()} worktrees · diff vs ${worktree.base}${worktree.truncated ? " · truncated" : ""}`}
          />
        </div>
      </main>
    </>
  );
}

export default async function ExplorerPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const worktree = await recordAdapter.sessionWorktree(readParam(await searchParams, "seat"));
  return (
    <Resolved
      reading={worktree}
      frame={(declared) => (
        <>
          <Chrome section="Explorer" />
          <main className="page">
            <div className="wrap">
              <Lede />
              <section className="panel" style={{ marginTop: "16px" }}>
                <header>
                  <h2>Worktree</h2>
                </header>
                {declared}
              </section>
              <RecordFoot readPath={SOURCE_LABELS.explorer} />
            </div>
          </main>
        </>
      )}
    >
      {(value) => <ExplorerBody worktree={value} />}
    </Resolved>
  );
}
