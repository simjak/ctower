import type { ReactElement } from "react";
import { NoSourceYet } from "@/frame/Declared";
import { NO_WORK_SESSIONS } from "@/read/futureSources";

const TOTALS = ["Sessions", "Work time", "Tokens", "Seats"] as const;

/**
 * The work timeline: who worked, for how long, at what token cost, with what
 * outcome. ctower records no session facts yet, so every total reads `—` and
 * the panel says so on its face. A number here would be a fabrication, and
 * this is the one panel of the approved set whose whole content is that fact.
 */
export function WorkTimeline(): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>Work timeline</h2>
        <span className="sub">who · what · duration · tokens · outcome</span>
      </header>
      <div className="totals">
        <div className="tgrid">
          {TOTALS.map((label) => (
            <div key={label}>
              <div className="k">{label}</div>
              <div className="v">—</div>
            </div>
          ))}
        </div>
      </div>
      <NoSourceYet title="no session data yet" source={NO_WORK_SESSIONS} />
    </section>
  );
}
