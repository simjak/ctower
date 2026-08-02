import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";
import { DeclaredState } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter } from "@/read/adapter";

export const dynamic = "force-dynamic";

const TOTALS = ["Registered beats", "Arriving", "Late", "Not arriving"] as const;
const COLUMNS = ["Seat", "Beat", "Schedule", "Last fire", "Next fire", "Health"] as const;

export default async function HeartbeatsPage(): Promise<ReactElement> {
  const registry = await recordAdapter.cadenceRegistry();
  return (
    <>
      <Chrome section="Heartbeats" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Heartbeats</h1>
            <p>
              Every scheduled wake in the portfolio: which seat owns it, the schedule it is
              registered under, when it last fired, when it fires next, and whether it is still
              arriving. A beat that stops arriving is how a seat goes quiet without anyone noticing.
            </p>
          </div>

          <div className="totals" style={{ padding: "16px 0 0" }}>
            <div className="tgrid">
              {TOTALS.map((label) => (
                <div key={label}>
                  <div className="k">{label}</div>
                  <div className="v">—</div>
                </div>
              ))}
            </div>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Cadence registry</h2>
              <span className="sub">no beat recorded</span>
            </header>
            <div className="tbl">
              <div className="tbl-head">
                {COLUMNS.map((column) => (
                  <div key={column}>{column}</div>
                ))}
              </div>
            </div>
            <DeclaredState reading={registry} />
          </section>

          <RecordFoot />
        </div>
      </main>
    </>
  );
}
