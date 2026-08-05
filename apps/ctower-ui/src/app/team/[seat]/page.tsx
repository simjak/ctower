import type { Metadata } from "next";
import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { KnownValue, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter, seatTerminalStreams, SOURCE_LABELS } from "@/read/adapter";
import type { CrewRoster, CrewRow, Reading, SessionStream } from "@/read/interface";
import { redacted } from "@/read/sources/redact";
import { LivePoll } from "@/surfaces/terminal/LivePoll";
import { IdleTerminalPane, LiveTerminalPane } from "@/surfaces/terminal/TerminalPane";

export const dynamic = "force-dynamic";

/**
 * A seat as a live console of its engagements.
 *
 * A **seat** is durable; a **crew** is one engagement of it. Org already
 * counts a seat's live crews in the grid — this page is where a click on
 * that row lands, and it shows each of those crews' own real panes rather
 * than averaging them into one status. Read-only, like every screen here:
 * this is Increment 1's console, not the composer.
 *
 * At most eight tabs render — a seat running more than eight crews at once
 * would be unusual, and the cap is stated on the page rather than a crew
 * silently missing its tab; see `design-reference/app.css`'s own note on the
 * CSS-only tab-switch technique this reuses from the Metrics scope radios.
 */
const TAB_CAP = 8;

function tabIdOf(index: number): string {
  return `term-tab-${index.toString()}`;
}

function TabGroup({
  engagements,
}: {
  readonly engagements: readonly {
    readonly crew: CrewRow;
    readonly stream: Reading<SessionStream>;
  }[];
}): ReactElement {
  const shown = engagements.slice(0, TAB_CAP);
  return (
    <div className="term-tabgroup">
      {shown.map((engagement, index) => (
        <input
          key={engagement.crew.name}
          type="radio"
          name="term-tab"
          id={tabIdOf(index)}
          className="term-tab-radio"
          defaultChecked={index === 0}
        />
      ))}
      {/* a <nav>, not a <div>: the CSS-only switch below counts `.term-pane`
          by tag position among its `.term-tabgroup` siblings, and a same-tag
          div here would shift every pane's count by one */}
      <nav className="term-tabs">
        {shown.map((engagement, index) => (
          <label key={engagement.crew.name} className="term-tab" htmlFor={tabIdOf(index)}>
            <b>{engagement.crew.name}</b>
            <span className="p">
              <KnownValue value={engagement.crew.project} /> ·{" "}
              <KnownValue value={engagement.crew.model} />
            </span>
          </label>
        ))}
      </nav>
      {shown.map((engagement) => {
        const identity = {
          crew: engagement.crew.name,
          seatInitials:
            engagement.crew.seatInitials.known === "value"
              ? engagement.crew.seatInitials.value
              : "··",
        };
        return (
          <div key={engagement.crew.name} className="term-pane">
            <Resolved reading={engagement.stream} subject={`${engagement.crew.name}'s pane`}>
              {(stream) =>
                stream.chosen === engagement.crew.sessionName ? (
                  <LiveTerminalPane identity={identity} stream={stream} />
                ) : (
                  <IdleTerminalPane
                    identity={identity}
                    headline="This crew's pane could not be confirmed"
                    detail="the pane read answered for a different session than the roster
                      listed a moment earlier; showing it would risk another crew's screen on
                      this tab, so this treats it the same as unavailable"
                    sourceLine="live tmux pane, capture-pane -p"
                    chip="mismatched read"
                  />
                )
              }
            </Resolved>
          </div>
        );
      })}
    </div>
  );
}

function SeatUnknown({
  seat,
  declared,
}: {
  readonly seat: string;
  readonly declared: readonly string[];
}): ReactElement {
  return (
    <>
      <Chrome section="Seat" back={{ href: "/team", label: "Org" }} />
      <main className="page">
        <div className="wrap">
          <div className="thead">
            <div className="crumbs">
              <Link href="/team">Org</Link>
              <span>/</span>
              <span className="id">{seat}</span>
            </div>
            <h1>
              <StateGlyph name="attn" />
              No declared seat by that name
            </h1>
          </div>
          <section className="panel" style={{ marginTop: "18px" }}>
            <header>
              <h2>Declared seats</h2>
            </header>
            <ul className="links">
              {declared.map((label) => (
                <li key={label}>
                  <span className="v">
                    <Link href={`/team/${encodeURIComponent(label)}`}>{label}</Link>
                  </span>
                </li>
              ))}
            </ul>
            <div className="src-line">
              <span>
                the personas directory declares the seat catalog; this name matches none of it
              </span>
            </div>
          </section>
          <RecordFoot readPath={SOURCE_LABELS.team} />
        </div>
      </main>
    </>
  );
}

function SeatBody({
  roster,
  seat,
  engagements,
}: {
  readonly roster: CrewRoster;
  readonly seat: string;
  readonly engagements: readonly {
    readonly crew: CrewRow;
    readonly stream: Reading<SessionStream>;
  }[];
}): ReactElement {
  const seatRow = roster.seats.find((row) => row.label === seat);
  if (seatRow === undefined) {
    return <SeatUnknown seat={seat} declared={roster.seats.map((row) => row.label)} />;
  }
  const count = engagements.length;
  return (
    <>
      <Chrome section="Seat" back={{ href: "/team", label: "Org" }} />
      <LivePoll />
      <main className="page">
        <div className="wrap">
          <div className="seat-id">
            <i className="av">{seatRow.initials}</i>
            <div>
              <h1>{seatRow.label}</h1>
            </div>
            <div className="live">
              <span className="num">{count}</span>
              <span className="k">{count === 1 ? "crew live" : "crews live"}</span>
            </div>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Live terminal</h2>
              <span className="sub">
                {count === 0
                  ? "no engagements right now"
                  : `${count.toString()} engagement${count === 1 ? "" : "s"}, one tab each`}
              </span>
            </header>
            {count === 0 ? (
              <div style={{ padding: "0 16px 16px" }}>
                <IdleTerminalPane
                  identity={{ crew: seatRow.label, seatInitials: seatRow.initials }}
                  headline="No live crews for this seat right now"
                  detail="tmux lists no session for this seat; Org's own grid and this page
                    read the same liveness source"
                  sourceLine="tmux list-sessions"
                  chip="0 live"
                />
              </div>
            ) : (
              <div style={{ margin: "0 16px 16px" }}>
                <TabGroup engagements={engagements} />
              </div>
            )}
            {count > TAB_CAP ? (
              <div className="src-line">
                <span>
                  {count} crews are live for this seat; only the first {TAB_CAP} render as tabs — a
                  stated cap, not a silent drop
                </span>
              </div>
            ) : null}
          </section>

          <div className="foot">
            <span>
              a seat&rsquo;s live terminal shows its crews&rsquo; real screens, not a summary of
              them
            </span>
            <span>everything above is read; nothing on this page writes</span>
          </div>

          <RecordFoot readPath={SOURCE_LABELS.team} />
        </div>
      </main>
    </>
  );
}

function Frame({
  seat,
  declared,
}: {
  readonly seat: string;
  readonly declared: ReactElement;
}): ReactElement {
  return (
    <>
      <Chrome section="Seat" back={{ href: "/team", label: "Org" }} />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Seat</h1>
            <p>A durable seat&rsquo;s live engagements, each showing its own real pane.</p>
          </div>
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>{seat}</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath={SOURCE_LABELS.team} />
        </div>
      </main>
    </>
  );
}

export async function generateMetadata({
  params,
}: {
  readonly params: Promise<{ readonly seat: string }>;
}): Promise<Metadata> {
  const { seat } = await params;
  return { title: `${redacted(seat)} · ctower` };
}

export default async function SeatPage({
  params,
}: {
  readonly params: Promise<{ readonly seat: string }>;
}): Promise<ReactNode> {
  const { seat } = await params;
  const roster = await recordAdapter.crewRoster(null, null);
  const engagements = await seatTerminalStreams(roster, seat);
  return (
    <Resolved reading={roster} frame={(declared) => <Frame seat={seat} declared={declared} />}>
      {(value) => <SeatBody roster={value} seat={seat} engagements={engagements} />}
    </Resolved>
  );
}
