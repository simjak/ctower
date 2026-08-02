import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";
import { DeclaredState } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter } from "@/read/adapter";

export const dynamic = "force-dynamic";

const BOUND_FACTS = [
  "Bound ticket",
  "Task file",
  "Worktree",
  "Branch",
  "Project",
  "Harness · model",
  "Persona",
  "Access",
] as const;

export default async function WorkspacePage(): Promise<ReactElement> {
  const workspace = await recordAdapter.sessionWorkspace();
  return (
    <>
      <Chrome section="Workspace" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Workspace</h1>
            <p>
              Everything a session is handed at the moment it starts, in one card. If a seat cannot
              say which ticket it is bound to and which worktree it is standing in, it should not be
              writing.
            </p>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Session start</h2>
              <span className="sub">no session recorded</span>
            </header>
            <ul className="kv">
              {BOUND_FACTS.map((label) => (
                <li key={label}>
                  <span className="k">{label}</span>
                  <span className="v">—</span>
                </li>
              ))}
            </ul>
            <DeclaredState reading={workspace} />
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Session states</h2>
              <span className="sub">no transition recorded</span>
            </header>
            <DeclaredState reading={workspace} />
          </section>

          <RecordFoot />
        </div>
      </main>
    </>
  );
}
