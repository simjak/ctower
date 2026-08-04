import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { KnownValue, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import type { SessionWorktree } from "@/read/interface";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import { FileDiffSwitch } from "@/surfaces/explorer/FileDiffSwitch";
import { readParam } from "@/surfaces/screenParams";
import { TreePane } from "@/surfaces/tree/TreePane";
import type { TreeRow } from "@/surfaces/tree/TreePane";

export const dynamic = "force-dynamic";

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Explorer</h1>
      <p>
        The session&rsquo;s own worktree, as it stands right now — and what it has actually changed
        against the trunk. A branch that claims work exists is not the same as a diff that shows it,
        and a diff is only as honest as the base it is measured from, so the base and its own commit
        are printed beside the branch.
      </p>
    </div>
  );
}

/** Changed files as a collapsed tree, changed directories opened to the selection. */
function changedRows(worktree: SessionWorktree): readonly TreeRow[] {
  const rows = new Map<string, TreeRow>();
  for (const file of worktree.files) {
    const parts = file.path.split("/");
    for (let index = 1; index < parts.length; index += 1) {
      const directory = parts.slice(0, index).join("/");
      rows.set(directory, { path: directory, depth: index - 1, isDirectory: true });
    }
    rows.set(file.path, {
      path: file.path,
      depth: parts.length - 1,
      isDirectory: false,
      badge: file.added === null ? "bin" : `+${file.added.toString()}`,
      badgeTone: "added",
    });
  }
  return [...rows.values()].sort((left, right) => left.path.localeCompare(right.path));
}

function DiffLines({ worktree }: { readonly worktree: SessionWorktree }): ReactElement {
  return (
    <div className="diff" style={{ fontSize: "12px" }}>
      {worktree.openDiff.map((line, index) => (
        <span
          className={line.kind === "context" ? "dl" : `dl ${line.kind}`}
          key={`${index.toString()}:${line.text}`}
        >
          {line.text}
        </span>
      ))}
      {worktree.openDiff.length === 0 ? (
        <span className="dl hunk">
          <KnownValue value={worktree.openDiffRead} />
        </span>
      ) : null}
    </div>
  );
}

function ExplorerBody({ worktree }: { readonly worktree: SessionWorktree }): ReactElement {
  const added = worktree.files.reduce((total, file) => total + (file.added ?? 0), 0);
  const removed = worktree.files.reduce((total, file) => total + (file.removed ?? 0), 0);
  // the ancestors of the open file start expanded; every other directory is closed
  const expanded =
    worktree.openPath === null
      ? []
      : worktree.openPath
          .split("/")
          .slice(0, -1)
          .map((_, index, parts) => parts.slice(0, index + 1).join("/"));

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
              <TreePane
                rows={changedRows(worktree)}
                openPath={worktree.openPath}
                expanded={expanded}
                route="/explorer"
                keepParams={{ seat: worktree.root }}
              />
              <div className="pane">
                <FileDiffSwitch
                  path={worktree.openPath ?? worktree.root}
                  file={
                    <>
                      <div className="pane-head" style={{ borderTop: 0 }}>
                        <span className="meta">
                          {worktree.files.length.toString()} files changed
                        </span>
                        <span className="meta" style={{ color: "var(--proven-deep)" }}>
                          +{added.toString()}
                        </span>
                        <span className="meta" style={{ color: "var(--refuse-deep)" }}>
                          −{removed.toString()}
                        </span>
                        <span className="spacer" />
                        {/* the base carries its own commit: a base 25 commits
                            behind the trunk is what made a six-file branch read
                            as 267 files (#236), and that is invisible unless the
                            base's age is on the screen beside the branch's */}
                        <span className="meta" title={worktree.base.note}>
                          <KnownValue value={worktree.branch} /> @{" "}
                          <KnownValue value={worktree.head} /> vs{" "}
                          <KnownValue value={worktree.base.ref} /> @{" "}
                          <KnownValue value={worktree.base.head} />
                        </span>
                      </div>
                      {/* the tree beside this already lists every changed file; the
                          pane states the selected one, so the page stays a tool
                          rather than becoming the flat dump the audit rejected */}
                      <ul className="commits" style={{ fontSize: "12px" }}>
                        {worktree.files
                          .filter((file) => file.path === worktree.openPath)
                          .map((file) => (
                            <li key={file.path}>
                              <span className="sha" style={{ color: "var(--proven-deep)" }}>
                                +{file.added?.toString() ?? "bin"}
                              </span>
                              <span className="sha" style={{ color: "var(--refuse-deep)" }}>
                                −{file.removed?.toString() ?? "bin"}
                              </span>
                              <span className="msg-t">{file.path}</span>
                              <span className="by">select Diff for its hunks</span>
                            </li>
                          ))}
                      </ul>
                    </>
                  }
                  diff={<DiffLines worktree={worktree} />}
                />
              </div>
            </div>
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.explorer}
            watermark={`${worktree.worktrees.length.toString()} worktrees on disk${worktree.reaped > 0 ? `, ${worktree.reaped.toString()} reaped and not shown` : ""} · ${worktree.base.note}${worktree.truncated ? " · truncated" : ""}`}
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
  const params = await searchParams;
  const worktree = await recordAdapter.sessionWorktree(
    readParam(params, "seat"),
    readParam(params, "path")
  );
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
