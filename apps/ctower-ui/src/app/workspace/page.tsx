import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { KnownValue, NoSourceYet, Resolved } from "@/frame/Declared";
import { NO_SESSION_STATES } from "@/read/futureSources";
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
    </div>
  );
}

/**
 * The screen renders whatever facts the source names.
 *
 * Round-1 review of PR #215 found this page hardcoding the interim source's
 * vocabulary — `bin/mux spawn`, "tmux session" — which made the adapter-only
 * swap claim untrue. It now knows only that a workspace is a list of labelled
 * facts and an optional start command, so a native source can replace the
 * interim one without a screen edit and without a false label.
 */
function WorkspaceBody({ workspace }: { readonly workspace: SessionWorkspace }): ReactElement {
  return (
    <>
      <Chrome section="Workspace" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <ChoiceTabs
            label="Choose a session"
            route="/workspace"
            selected={workspace.chosen}
            choices={workspace.choices.map((choice) => ({ key: choice, label: choice }))}
          />

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Session start</h2>
              <span className="sub">{workspace.sourceNote}</span>
            </header>
            <ul className="kv">
              {workspace.facts.map((entry) => (
                <li key={entry.label}>
                  <span className="k">{entry.label}</span>
                  <span className="v">
                    <KnownValue value={entry.value} />
                    {entry.detail === null ? null : <span className="sub">{entry.detail}</span>}
                  </span>
                </li>
              ))}
            </ul>
            <div className="kv">
              <li>
                <span className="k">Start command</span>
                <span className="v">
                  <KnownValue
                    value={workspace.startCommand}
                    render={(text) => <pre className="cmdblock">{text}</pre>}
                  />
                </span>
              </li>
            </div>
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Session states</h2>
              <span className="sub">who · what · duration · outcome</span>
            </header>
            <NoSourceYet title="no session transitions yet" source={NO_SESSION_STATES} />
          </section>

          <RecordFoot
            readPath={SOURCE_LABELS.workspace}
            watermark={`${workspace.choices.length.toString()} sessions offered by this source`}
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
