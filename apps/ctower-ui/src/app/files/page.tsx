import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { INERT_CONTROL } from "@/frame/inert";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { clockText, dayText } from "@/read/elapsed";
import type { AuthoredFiles } from "@/read/interface";
import { TreePane } from "@/surfaces/tree/TreePane";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Files</h1>
    </div>
  );
}

/** The caveat both inert controls carry, in a hover rather than on the page. */
const SAVE_GATE =
  "a save would open a branch off main, one commit and a pull request against protected main, and nothing is written until that pull request merges under cross-family review — this surface opens none of it";

function EditorFoot(): ReactElement {
  return (
    <>
      <div className="editor-foot">
        <button className="btn" disabled style={INERT_CONTROL} title={SAVE_GATE} type="button">
          Save
        </button>
        <button
          className="btn ghost"
          disabled
          style={INERT_CONTROL}
          title={SAVE_GATE}
          type="button"
        >
          Revert
        </button>
        <span className="verdict v-held" title={SAVE_GATE}>
          read-only
        </span>
      </div>
    </>
  );
}

function FilesBody({ files }: { readonly files: AuthoredFiles }): ReactElement {
  // only the ancestors of the open file start expanded; the rest stay closed
  const expanded =
    files.openPath === null
      ? []
      : files.openPath
          .split("/")
          .slice(0, -1)
          .map((_, index, parts) => parts.slice(0, index + 1).join("/"));
  return (
    <>
      <Chrome section="Files" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <section className="panel" style={{ marginTop: "16px" }}>
            <div className="ed">
              <TreePane
                rows={files.entries.map((entry) => ({
                  path: entry.path,
                  depth: entry.depth,
                  isDirectory: entry.isDirectory,
                }))}
                openPath={files.openPath}
                expanded={expanded}
                route="/files"
              />
              <div className="pane">
                <div className="pane-head">
                  <span className="path">{files.openPath ?? "—"}</span>
                  <span className="spacer" />
                  <span className="meta">
                    {files.root} @ {files.revision}
                  </span>
                </div>
                <pre className="code" style={{ fontSize: "12px" }}>
                  {files.openLines.map((line, index) => (
                    <span className="l" key={`${index.toString()}:${line}`}>
                      {line}
                    </span>
                  ))}
                </pre>
                <EditorFoot />
              </div>
            </div>
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Recent commits</h2>
              <span className="sub">this path · last {files.commits.length.toString()}</span>
            </header>
            <ul className="commits">
              {files.commits.map((commit) => (
                <li key={commit.sha}>
                  <span className="sha">{commit.sha}</span>
                  <span className="msg-t">{commit.subject}</span>
                  <span className="by">
                    {commit.author} · {dayText(commit.at)} {clockText(commit.at)}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.files}
            watermark={
              files.truncated
                ? `showing ${files.shownTotal.toString()} of ${files.sourceTotal.toString()} files at ${files.revision} — this tree is capped for the browser and is not the whole repository`
                : `all ${files.sourceTotal.toString()} files at ${files.revision} · browse only`
            }
          />
        </div>
      </main>
    </>
  );
}

export default async function FilesPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const files = await recordAdapter.authoredFiles(readParam(await searchParams, "path"));
  return (
    <Resolved
      reading={files}
      frame={(declared) => (
        <>
          <Chrome section="Files" />
          <main className="page">
            <div className="wrap">
              <Lede />
              <section className="panel" style={{ marginTop: "16px" }}>
                <header>
                  <h2>Tree</h2>
                </header>
                {declared}
                <EditorFoot />
              </section>
              <RecordFoot readPath={SOURCE_LABELS.files} />
            </div>
          </main>
        </>
      )}
    >
      {(value) => <FilesBody files={value} />}
    </Resolved>
  );
}
