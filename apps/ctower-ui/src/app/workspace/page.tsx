import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { NoSourceYet, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import type { SessionWorkspace } from "@/read/interface";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Workspace</h1>
      <p>
        Everything a session is handed at the moment it starts, in one card. If a seat cannot say
        which ticket it is bound to and which worktree it is standing in, it should not be writing.
      </p>
    </div>
  );
}

function Row({
  label,
  value,
  sub,
}: {
  readonly label: string;
  readonly value: string;
  readonly sub?: string;
}): ReactElement {
  return (
    <li>
      <span className="k">{label}</span>
      <span className="v">
        {value}
        {sub === undefined ? null : <span className="sub">{sub}</span>}
      </span>
    </li>
  );
}

function WorkspaceBody({ workspace }: { readonly workspace: SessionWorkspace }): ReactElement {
  const spawn = [
    `bin/mux spawn ${workspace.crew} \\`,
    `  --cwd ${workspace.cwd} \\`,
    `  -- ${workspace.harness} ...`,
  ].join("\n");
  return (
    <>
      <Chrome section="Workspace" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <ChoiceTabs
            label="Choose a crew"
            route="/workspace"
            selected={workspace.crew}
            choices={workspace.crews.map((crew) => ({ key: crew, label: crew }))}
          />

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Session start</h2>
              <span className="sub">{workspace.crew}</span>
            </header>
            <ul className="kv">
              <Row label="Crew" value={workspace.crew} sub={`tmux session ${workspace.session}`} />
              <Row
                label="Worktree"
                value={workspace.cwd}
                sub={
                  workspace.project === null
                    ? "not a git checkout"
                    : `repository ${workspace.project}`
                }
              />
              <Row
                label="Branch"
                value={
                  workspace.branch === null
                    ? "no branch recorded"
                    : `${workspace.branch}${workspace.head === null ? "" : ` @ ${workspace.head}`}`
                }
                {...(workspace.headSubject === null ? {} : { sub: workspace.headSubject })}
              />
              <Row
                label="Harness"
                value={workspace.harness}
                sub="from the capture bridge's crew list"
              />
            </ul>
            <pre className="cmdblock">{spawn}</pre>
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Session states</h2>
              <span className="sub">who · what · duration · outcome</span>
            </header>
            <NoSourceYet
              title="no session transitions yet"
              source={{
                lands: "G5",
                what: "a session's recorded state transitions — dispatched, briefed, working, gated",
              }}
            />
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.workspace}
            watermark={`${workspace.crews.length.toString()} live crews on the bridge`}
          />
        </div>
      </main>
    </>
  );
}

export default async function WorkspacePage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const workspace = await recordAdapter.sessionWorkspace(readParam(await searchParams, "seat"));
  return (
    <Resolved
      reading={workspace}
      frame={(declared) => (
        <>
          <Chrome section="Workspace" />
          <main className="page">
            <div className="wrap">
              <Lede />
              <section className="panel" style={{ marginTop: "16px" }}>
                <header>
                  <h2>Session start</h2>
                </header>
                {declared}
              </section>
              <RecordFoot readPath={SOURCE_LABELS.workspace} />
            </div>
          </main>
        </>
      )}
    >
      {(value) => <WorkspaceBody workspace={value} />}
    </Resolved>
  );
}
