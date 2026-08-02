import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { INERT_CONTROL } from "@/frame/inert";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { clockText, dayText } from "@/read/elapsed";
import type { AuthoredFiles } from "@/read/interface";
import { FileTree } from "@/surfaces/files/FileTree";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Files</h1>
      <p>
        Souls, skills, harness guides, project rules and repo files, browsed at the revision the
        repository actually holds. There is no quiet write path: saving would open a branch and a
        pull request, and the same review and CSO gates that hold for code hold for a soul.
      </p>
    </div>
  );
}

function EditorFoot(): ReactElement {
  return (
    <>
      <div className="gate-note show">
        a save would open a branch off main, one commit, and a pull request against protected main ·
        requires: review sign-off (cross-family) · nothing is written until that pull request merges
        — and read-only v1 opens none of it
      </div>
      <div className="editor-foot">
        <button className="btn" type="button" disabled style={INERT_CONTROL}>
          Save — commit via review
        </button>
        <button className="btn ghost" type="button" disabled style={INERT_CONTROL}>
          Revert
        </button>
        <span className="note">
          Read-only v1: this surface browses a committed revision and holds no authority to write,
          so both controls are inert by design.
        </span>
      </div>
    </>
  );
}

function FilesBody({ files }: { readonly files: AuthoredFiles }): ReactElement {
  return (
    <>
      <Chrome section="Files" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <section className="panel" style={{ marginTop: "16px" }}>
            <div className="ed">
              <FileTree entries={files.entries} openPath={files.openPath} route="/files" />
              <div className="pane">
                <div className="pane-head">
                  <span className="path">{files.openPath ?? "—"}</span>
                  <span className="spacer" />
                  <span className="meta">
                    {files.root} @ {files.revision}
                  </span>
                </div>
                <pre className="code">
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
            watermark={`${files.entries.length.toString()} tree rows at ${files.revision} · browse only`}
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
