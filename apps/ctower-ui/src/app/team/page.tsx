import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { KnownValue, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import type { CrewRoster, CrewRow, ModelShare, ProjectRoster, TailNote } from "@/read/interface";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import type { TabCount } from "@/surfaces/ChoiceTabs";
import { readParam } from "@/surfaces/screenParams";

export const dynamic = "force-dynamic";

/**
 * Org — the who layer.
 *
 * A **seat** is durable: one accountable persona that outlives every job it
 * does. A **crew** is one engagement of that seat. The grid counts seats across
 * projects; the roster under it is every crew alive on the fleet right now.
 *
 * Nothing here is a number this screen chose. Liveness is the session listing,
 * the model, task, status and project are the crew log's own fields, and the
 * seats are the persona files. A field the record is silent about says so on
 * the row, and a field whose read failed says *that* instead — the two are
 * never drawn the same way.
 */

const GLYPH = { "in-flight": "flight", parked: "parked", held: "held" } as const;

/**
 * Which of the three chart tokens a model's band uses. Keyed on the model name
 * so the same family keeps the same colour between reads; the legend repeats
 * every label and count, so nothing is told apart by hue alone.
 */
function bandOf(model: ModelShare): string {
  const name = model.label.toLowerCase();
  if (name.startsWith("opus")) {
    return "m-opus";
  }
  return name.startsWith("fable") ? "m-fable" : "m-sol";
}

function ActivityMark({ row }: { readonly row: CrewRow }): ReactElement {
  if (row.activity === "unrecorded") {
    return (
      <span className="c-stat idle">
        <KnownValue value={row.status} />
      </span>
    );
  }
  const tone =
    row.activity === "held"
      ? "c-stat blocked"
      : row.activity === "parked"
        ? "c-stat idle"
        : "c-stat";
  return (
    <span className={tone}>
      <StateGlyph name={GLYPH[row.activity]} />
      <KnownValue value={row.status} />
    </span>
  );
}

function Crew({
  row,
  spellOut,
}: {
  readonly row: CrewRow;
  readonly spellOut: boolean;
}): ReactElement {
  return (
    <div className="crow">
      <i className="av">
        <KnownValue value={row.seatInitials} render={(mark) => mark} />
      </i>
      <span className="c-crew">
        <b>{row.name}</b>
        <span className="parse">
          <KnownValue value={row.seatLabel} />
          <i>·</i>
          {row.request.known === "value" ? (
            <span>{row.request.value}</span>
          ) : (
            <span className="miss">
              <KnownValue value={row.request} />
            </span>
          )}
          <i>·</i>
          <KnownValue value={row.slug} />
        </span>
      </span>
      <span className="c-proj">
        <span className="chip proj">
          <KnownValue value={row.project} />
        </span>
      </span>
      <span className="c-model">
        <span className="mono">
          <KnownValue value={row.model} />
        </span>
        <span className="harness">
          <KnownValue value={row.harness} />
        </span>
      </span>
      <span className="c-task">
        <KnownValue value={row.task} />
      </span>
      <ActivityMark row={row} />
      <span className="c-live">
        <span>
          <KnownValue value={row.upFor} />
        </span>
        <span>
          <KnownValue value={row.loggedAgo} />
        </span>
      </span>
      {row.flag === null ? null : (
        <span className="flag" title={row.flag}>
          {spellOut ? row.flag : "no request id"}
        </span>
      )}
    </div>
  );
}

function Group({
  group,
  spellOutFor,
}: {
  readonly group: ProjectRoster;
  readonly spellOutFor: string | null;
}): ReactElement {
  const counted = [
    `${String(group.crews.length)} ${group.crews.length === 1 ? "crew" : "crews"}`,
    `${String(group.inFlight)} in flight`,
    `${String(group.parked)} parked`,
    `${String(group.held)} held`,
  ];
  return (
    <section className="pgroup">
      <div className="pg-head">
        <i className="swatch" />
        <h2>{group.label}</h2>
        <span className="count">{counted.join(" · ")}</span>
      </div>
      <div className="panel">
        <div className="crow-head">
          <span />
          <span>Crew — who · why · what</span>
          <span>Project</span>
          <span>Model</span>
          <span>Current task</span>
          <span>State</span>
          <span>Liveness</span>
        </div>
        {group.crews.map((row) => (
          <Crew key={row.name} row={row} spellOut={row.name === spellOutFor} />
        ))}
      </div>
    </section>
  );
}

function Matrix({ roster }: { readonly roster: CrewRoster }): ReactElement {
  // the vendored grid sizes four fixed project columns; the fleet decides how
  // many there actually are, so the count comes from the data
  const wide = 150 + (roster.columns.length + 1) * 58;
  const columns = {
    gridTemplateColumns: `minmax(150px, 1fr) repeat(${String(roster.columns.length + 1)}, minmax(46px, 58px))`,
    minWidth: `${String(wide)}px`,
  };
  // the fleet decides how many project columns there are, so on a phone the
  // grid scrolls inside its own panel rather than crushing the seat names or
  // pushing the page sideways
  return (
    <div className="org" style={{ overflowX: "auto" }}>
      <div className="org-head" style={columns}>
        <span>Seat</span>
        {roster.columns.map((column) => (
          <span key={column} title={column}>
            {column}
          </span>
        ))}
        <span className="t">all</span>
      </div>
      {roster.seats.map((seat) => (
        <div className="org-row" key={seat.seat} style={columns}>
          <span className="s">
            <i className="av">{seat.initials}</i>
            <span className="nm">{seat.label}</span>
          </span>
          {seat.perProject.map((count, index) => (
            <span
              className={count === 0 ? "c" : "c on"}
              key={roster.columns[index] ?? String(index)}
            >
              {count === 0 ? "·" : count}
            </span>
          ))}
          <span className={seat.total === 0 ? "c t" : "c t on"}>{seat.total}</span>
        </div>
      ))}
      <div className="org-row org-total" style={{ ...columns, background: "var(--surface)" }}>
        <span
          className="s"
          style={{
            color: "var(--ink-3)",
            fontSize: "11px",
            letterSpacing: ".06em",
            textTransform: "uppercase",
          }}
        >
          Live crews
        </span>
        {roster.columnTotals.map((count, index) => (
          <span className={count === 0 ? "c" : "c on"} key={roster.columns[index] ?? String(index)}>
            {count}
          </span>
        ))}
        <span className="c t on">{roster.total}</span>
      </div>
    </div>
  );
}

function TailLine({ tail }: { readonly tail: TailNote }): ReactElement {
  const notes = [
    `${tail.totalLines.toString()} complete crew-log lines`,
    tail.partialTail ? "1 line at the tail was mid-write and is not shown" : "no partial tail",
    tail.malformed === 0 ? "none malformed" : `${tail.malformed.toString()} malformed`,
  ];
  return <span>{notes.join(" · ")}</span>;
}

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Who is working, on what, right now</h1>
      <p>
        A <b>seat</b> is durable — one accountable persona that outlives every job it does. A{" "}
        <b>crew</b> is one engagement of that seat: a live session with a model, a project and one
        task. The grid below counts seats across projects; the roster under it is every crew alive
        on the fleet.
      </p>
    </div>
  );
}

/**
 * A filter chip's number, carrying the unit it counts in. Each one counts what
 * clicking it would reveal *under the other filter*, which is why the detail
 * says so rather than leaving the reader to assume a fleet-wide number.
 */
function crews(count: number): TabCount {
  return {
    value: count,
    unit: count === 1 ? "crew" : "crews",
    detail: `${count.toString()} live ${count === 1 ? "crew" : "crews"} this filter would show, counted under the other filter's current selection`,
  };
}

function TeamBody({ roster }: { readonly roster: CrewRoster }): ReactElement {
  // the design audit's F-004 rule, applied to the row flag: the first offending
  // row carries the whole sentence, every later one carries the fact alone
  const spellOutFor =
    roster.groups.flatMap((group) => group.crews).find((row) => row.flag !== null)?.name ?? null;
  const keeping = roster.selectedSeat === null ? {} : { seat: roster.selectedSeat };
  const keepingSeat = roster.selectedProject === null ? {} : { project: roster.selectedProject };
  return (
    <>
      <Chrome section="Org" />
      <main className="page">
        <div className="wrap">
          <Lede />

          <ChoiceTabs
            label="Filter by project"
            route="/team"
            parameter="project"
            selected={roster.selectedProject ?? ""}
            keeping={keeping}
            choices={[
              { key: "", label: "All projects", count: crews(roster.allProjectsCount) },
              ...roster.projectFilters.map((filter) => ({
                key: filter.key,
                label: filter.label,
                count: crews(filter.count),
              })),
            ]}
          />

          <ChoiceTabs
            label="Filter by seat"
            route="/team"
            parameter="seat"
            selected={roster.selectedSeat ?? ""}
            keeping={keepingSeat}
            choices={[
              { key: "", label: "All seats", count: crews(roster.allSeatsCount) },
              ...roster.seatFilters.map((filter) => ({
                key: filter.key,
                label: filter.label,
                count: crews(filter.count),
              })),
            ]}
          />

          <section className="panel" style={{ marginTop: "18px" }}>
            <header>
              <h2>Seats × projects</h2>
              <span className="sub">live crews per seat</span>
            </header>
            <Matrix roster={roster} />
            <div className="src-line">
              <span>{roster.sourceNote}</span>
              <span>{roster.seatSource}</span>
              {roster.unseated === 0 ? null : (
                <span>
                  {roster.unseated} live {roster.unseated === 1 ? "crew is" : "crews are"} in the
                  roster below but in no grid row: the name matches no declared seat
                </span>
              )}
            </div>
          </section>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Right now</h2>
              <span className="sub">counted from the rows below, not reported</span>
            </header>
            <div className="totals">
              <div className="tgrid">
                <div>
                  <div className="k">Crews live</div>
                  <div className="v">{roster.total}</div>
                </div>
                <div>
                  <div className="k">In flight</div>
                  <div className="v">{roster.inFlight}</div>
                </div>
                <div>
                  <div className="k">Parked</div>
                  <div className="v">{roster.parked}</div>
                </div>
                <div>
                  <div className="k">Held</div>
                  <div className="v">{roster.held}</div>
                </div>
              </div>

              <div className="split">
                <div className="lbl">
                  <span>Model</span>
                  <span>
                    {roster.total} {roster.total === 1 ? "crew" : "crews"}
                  </span>
                </div>
                <div className="bar-split">
                  {roster.models.map((model) => (
                    <span
                      key={model.label}
                      className={bandOf(model)}
                      style={{ flex: model.count }}
                    />
                  ))}
                </div>
                <div className="legend">
                  {roster.models.map((model) => (
                    <span key={model.label}>
                      <i className={bandOf(model)} />
                      {model.label} · {model.count}
                      {model.harness.known === "value" ? ` · ${model.harness.value}` : null}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <div className="src-line">
              <span>{roster.activityRule}</span>
              <span>
                model strings are the log&rsquo;s own, unnormalised: two spellings of one family
                stay two rows rather than being merged into a number nobody recorded
              </span>
              {roster.unrecorded === 0 ? null : (
                <span>
                  {roster.unrecorded} of these {roster.total} carry no status in the log and are
                  counted in none of the three
                </span>
              )}
            </div>
          </section>

          {roster.groups.map((group) => (
            <Group key={group.key} group={group} spellOutFor={spellOutFor} />
          ))}

          <div className="foot">
            <span>
              every crew is{" "}
              <span className="mono">&lt;persona&gt;-&lt;request&gt;-&lt;slug&gt;</span> — the name
              alone says who is accountable, which request it serves, and what it does
            </span>
            <span>a name with no request id is flagged, not hidden</span>
          </div>

          <RecordFoot readPath={SOURCE_LABELS.team} watermark={<TailLine tail={roster.tail} />} />
        </div>
      </main>
    </>
  );
}

function TeamFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Org" />
      <main className="page">
        <div className="wrap">
          <Lede />
          <section className="panel" style={{ marginTop: "18px" }}>
            <header>
              <h2>Seats × projects</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath={SOURCE_LABELS.team} />
        </div>
      </main>
    </>
  );
}

export default async function TeamPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const params = await searchParams;
  const roster = await recordAdapter.crewRoster(
    readParam(params, "project"),
    readParam(params, "seat")
  );
  return (
    <Resolved reading={roster} frame={(declared) => <TeamFrame declared={declared} />}>
      {(value) => <TeamBody roster={value} />}
    </Resolved>
  );
}
