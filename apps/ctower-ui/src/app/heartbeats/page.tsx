import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { clockText, dayText } from "@/read/elapsed";
import type { Beat, BeatHealth, CadenceRegistry } from "@/read/interface";

export const dynamic = "force-dynamic";

const COLUMNS = ["Seat", "Beat", "Schedule", "Last fire", "Next fire", "Health"] as const;

const HEALTH_CLASS: Readonly<Record<BeatHealth, string>> = {
  alive: "verdict v-pass",
  late: "verdict v-changes",
  dead: "verdict v-held",
  unknown: "verdict v-filed",
};

/**
 * What each mark is called on the row, matching its tile. `unknown` reads as
 * "liveness unestablished" because the row is a statement about this source's
 * marker registry, not about the beat — a beat cron holds and fires is not in an
 * unknown state, it is in an unread one (#238).
 */
const HEALTH_LABEL: Readonly<Record<BeatHealth, string>> = {
  alive: "arriving",
  late: "late",
  dead: "not arriving",
  unknown: "liveness unestablished",
};

function stamp(value: string | null): string {
  return value === null ? "—" : `${dayText(value)} ${clockText(value)}`;
}

function BeatRow({ beat }: { readonly beat: Beat }): ReactElement {
  return (
    <div className="hb">
      <div className="cell c-seat">
        <span className="lbl">seat</span>
        {beat.seat}
      </div>
      <div className="cell c-beat">
        <span className="lbl">beat</span>
        {beat.beat}
      </div>
      <div className="cell c-cron">
        <span className="lbl">cron</span>
        <span className="mono">{beat.schedule}</span>
      </div>
      <div className="cell c-last">
        <span className="lbl">last fire</span>
        <span className="mono">{stamp(beat.lastFire)}</span>
      </div>
      <div className="cell c-next">
        <span className="lbl">next fire</span>
        <span className="mono">{stamp(beat.nextFire)}</span>
      </div>
      <div className="cell c-health">
        <span className={HEALTH_CLASS[beat.health]}>{HEALTH_LABEL[beat.health]}</span>
      </div>
      {beat.why === null ? null : (
        <div className={beat.health === "dead" ? "why dead" : "why"}>{beat.why}</div>
      )}
    </div>
  );
}

/**
 * The summary strip. Every registered beat lands in exactly one of the four
 * marks, so the tiles add up to the registry on their face — a beat whose
 * liveness could not be established is counted and named, not left as the
 * difference between two numbers the reader has to subtract (#238).
 */
function Totals({ registry }: { readonly registry: CadenceRegistry }): ReactElement {
  const cells: readonly (readonly [string, number])[] = [
    ["Registered beats", registry.registered],
    ["Arriving", registry.arriving],
    ["Late", registry.late],
    ["Not arriving", registry.notArriving],
    ["Liveness unestablished", registry.unaccounted],
  ];
  return (
    <div className="totals" style={{ padding: "16px 0 0" }}>
      <div className="tgrid">
        {cells.map(([label, value]) => (
          <div key={label}>
            <div className="k">{label}</div>
            <div className="v">{value}</div>
          </div>
        ))}
      </div>
      <div className="src-line">
        <span>
          the last four add up to the registry: {registry.arriving} arriving + {registry.late} late
          + {registry.notArriving} not arriving + {registry.unaccounted} unestablished ={" "}
          {registry.registered} registered
        </span>
        {registry.unaccounted === 0 ? null : (
          <span>
            {registry.unaccounted} of these {registry.registered} write no fire marker this source
            reads, so they can go neither green nor red here — that is a gap in the marker registry,
            not a verdict on the beat
          </span>
        )}
      </div>
    </div>
  );
}

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Heartbeats</h1>
      <p>
        Every scheduled wake this source registers: who owns it, the schedule it is registered
        under, when it last fired, when it fires next, and whether it is still arriving. A beat that
        stops arriving is how a seat goes quiet without anyone noticing. The source is named under
        the registry — it is one host&rsquo;s schedule, not yet the whole portfolio&rsquo;s.
      </p>
    </div>
  );
}

function Registry({ registry }: { readonly registry: CadenceRegistry }): ReactElement {
  return (
    <>
      <Chrome section="Heartbeats" />
      <main className="page">
        <div className="wrap">
          <Lede />
          <Totals registry={registry} />
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Cadence registry</h2>
              <span className="sub">
                {registry.sourceLabel} · swept {clockText(registry.sweptAt)}
              </span>
            </header>
            <div className="tbl">
              <div className="tbl-head">
                {COLUMNS.map((column) => (
                  <div key={column}>{column}</div>
                ))}
              </div>
              {registry.beats.map((beat) => (
                <BeatRow beat={beat} key={`${beat.seat}-${beat.beat}`} />
              ))}
            </div>
          </section>
          <RecordFoot readPath={SOURCE_LABELS.heartbeats} watermark={registry.healthRule} />
        </div>
      </main>
    </>
  );
}

export default async function HeartbeatsPage(): Promise<ReactNode> {
  const registry = await recordAdapter.cadenceRegistry();
  return (
    <Resolved
      reading={registry}
      frame={(declared) => (
        <>
          <Chrome section="Heartbeats" />
          <main className="page">
            <div className="wrap">
              <Lede />
              <section className="panel" style={{ marginTop: "16px" }}>
                <header>
                  <h2>Cadence registry</h2>
                </header>
                {declared}
              </section>
              <RecordFoot readPath={SOURCE_LABELS.heartbeats} />
            </div>
          </main>
        </>
      )}
    >
      {(value) => <Registry registry={value} />}
    </Resolved>
  );
}
