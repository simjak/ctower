import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { KnownValue, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import type { CrewActivity, CrewRoster, CrewRow, ProjectRoster } from "@/read/interface";
import { Count } from "@/surfaces/Count";
import { ActivityMark } from "@/surfaces/crew/marks";

export const dynamic = "force-dynamic";

/**
 * Live — what the fleet is doing this minute.
 *
 * Org answers *who works here*: a durable roster, sorted by name, the same list
 * whether or not anything is running. This screen answers a different question —
 * *what is running right now, and who is on it* — so it sorts by what needs the
 * operator instead: held first, then in flight, then parked, and last the crews
 * the record holds no status for.
 *
 * It reads the same record Org reads. There is no new operation behind this
 * screen and it makes no claim the roster does not already carry:
 *
 * - **No liveness.** G1 does not exist. What a row shows is the status the crew
 *   *recorded*, not an observation of the substrate, and the header says so
 *   rather than letting a recorded word read as a live one.
 * - **No workflow stage.** No read on the authored surface returns one.
 * - **No diffs.** The `+N −N` a lane produced is a separate worktree read; this
 *   slice does not join it rather than printing a number it did not compute.
 */

/**
 * Held first, because a held crew is the one thing on this screen that is
 * waiting for a person. `unrecorded` sorts last: a crew the log is silent about
 * is not idle, and putting it above a parked crew would rank an absence of
 * information above a recorded fact.
 */
const URGENCY: Readonly<Record<CrewActivity, number>> = {
  held: 0,
  "in-flight": 1,
  parked: 2,
  unrecorded: 3,
};

function byUrgency(left: CrewRow, right: CrewRow): number {
  const rank = URGENCY[left.activity] - URGENCY[right.activity];
  return rank === 0 ? left.name.localeCompare(right.name) : rank;
}

function Lane({ row }: { readonly row: CrewRow }): ReactElement {
  return (
    <Link className="crow" href={`/crew/${encodeURIComponent(row.name)}`}>
      <i className="av">
        <KnownValue value={row.seatInitials} render={(mark) => mark} />
      </i>
      <span className="c-crew">
        <b>{row.name}</b>
        <span className="parse">
          <KnownValue value={row.seatLabel} />
          <i>·</i>
          <span className="mono">
            <KnownValue value={row.harness} />
          </span>
        </span>
      </span>
      <span className="c-task">
        <KnownValue value={row.task} />
      </span>
      <ActivityMark activity={row.activity} status={row.status} />
      <span className="c-live">
        <span>
          <KnownValue value={row.upFor} />
        </span>
        <span>
          <KnownValue value={row.loggedAgo} />
        </span>
      </span>
    </Link>
  );
}

function Running({ group }: { readonly group: ProjectRoster }): ReactElement {
  const lanes = [...group.crews].sort(byUrgency);
  return (
    <section className="panel" style={{ marginTop: "14px" }}>
      <header>
        <h2>{group.label}</h2>
        <Count value={lanes.length} unit={lanes.length === 1 ? "lane" : "lanes"} />
        <Count value={group.held} unit="held" detail="crews waiting on a person" />
      </header>
      <div className="rows">
        {lanes.map((row) => (
          <Lane key={row.name} row={row} />
        ))}
      </div>
    </section>
  );
}

function LiveBody({ roster }: { readonly roster: CrewRoster }): ReactElement {
  // a project with nothing running is not what this screen is for: Org already
  // lists every project whether or not it has a lane alive in it
  const running = roster.groups.filter((group) => group.crews.length > 0);
  return (
    <>
      <Chrome section="Live" />
      <main className="page">
        <div className="wrap">
          <p className="lede">Recorded, not observed. Ordered by what needs you.</p>
          {running.length === 0 ? (
            <section className="panel" style={{ marginTop: "14px" }}>
              <header>
                <h2>Nothing running</h2>
              </header>
              <p className="lede">
                Nothing is running. <Link href="/team">See every seat</Link>
              </p>
            </section>
          ) : (
            running.map((group) => <Running key={group.key} group={group} />)
          )}
          <RecordFoot readPath={SOURCE_LABELS.team} />
        </div>
      </main>
    </>
  );
}

function LiveFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Live" />
      <main className="page">
        <div className="wrap">
          <section className="panel" style={{ marginTop: "14px" }}>
            <header>
              <h2>What is running</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath={SOURCE_LABELS.team} />
        </div>
      </main>
    </>
  );
}

export default async function LivePage(): Promise<ReactNode> {
  const roster = await recordAdapter.crewRoster(null, null);
  return (
    <Resolved reading={roster} frame={(declared) => <LiveFrame declared={declared} />}>
      {(value) => <LiveBody roster={value} />}
    </Resolved>
  );
}
