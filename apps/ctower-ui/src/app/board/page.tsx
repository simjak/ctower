import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter } from "@/read/adapter";
import { sourceKindOf, unresolvedSources } from "@/read/boardProjection";
import type { BoardEntry, BoardSnapshot } from "@/read/interface";
import { LaneCard } from "@/surfaces/board/LaneCard";
import { SourceTabs } from "@/surfaces/board/SourceTabs";
import { UnreadSources } from "@/surfaces/board/UnreadSources";
import type { SourceTab } from "@/surfaces/board/SourceTabs";
import {
  ALL_SOURCES,
  countHeld,
  countInFlight,
  inLane,
  LANE_COLUMNS,
  selectEntries,
  sourceKinds,
} from "@/surfaces/board/lanes";

export const dynamic = "force-dynamic";

function readSource(value: string | string[] | undefined): string {
  if (typeof value === "string" && value !== "") {
    return value;
  }
  return ALL_SOURCES;
}

function tabsFor(entries: readonly BoardEntry[], kinds: readonly string[]): readonly SourceTab[] {
  return [
    { key: ALL_SOURCES, label: "All sources", count: entries.length },
    ...kinds.map((kind) => ({
      key: kind,
      label: kind,
      count: entries.filter((entry) => sourceKindOf(entry) === kind).length,
    })),
  ];
}

function Counters({ entries }: { readonly entries: readonly BoardEntry[] }): ReactElement {
  return (
    <span className="counters">
      <span className="ctr c-flight">
        <StateGlyph name="flight" />
        <span className="n">{countInFlight(entries)}</span>
      </span>
      <span className="ctr c-held">
        <StateGlyph name="held" />
        <span className="n">{countHeld(entries)}</span>
      </span>
    </span>
  );
}

function StageJump({ entries }: { readonly entries: readonly BoardEntry[] }): ReactElement {
  return (
    <nav className="stagejump" aria-label="Jump to lane">
      {LANE_COLUMNS.map((column) => (
        <a className="sj" href={`#${column.anchor}`} key={column.lane}>
          <i className={`bar ${column.bar}`} />
          {column.title.toLowerCase()}{" "}
          <span className="n">{inLane(entries, column.lane).length}</span>
        </a>
      ))}
    </nav>
  );
}

function Rail({
  entries,
  now,
}: {
  readonly entries: readonly BoardEntry[];
  readonly now: number;
}): ReactElement {
  return (
    <main className="rail">
      {LANE_COLUMNS.map((column) => {
        const cards = inLane(entries, column.lane);
        return (
          <section className="col" id={column.anchor} key={column.lane}>
            <div className="col-head">
              <i className={`bar ${column.bar}`} />
              <h2>{column.title}</h2>
              <span className="count">{cards.length}</span>
            </div>
            <div className="stack">
              {cards.map((entry) => (
                <LaneCard entry={entry} key={entry.card.ticketId} now={now} />
              ))}
              {cards.length === 0 ? (
                <div className="col-empty" style={{ display: "block" }}>
                  {column.emptyText}
                </div>
              ) : null}
            </div>
          </section>
        );
      })}
    </main>
  );
}

function BoardBody({
  snapshot,
  source,
}: {
  readonly snapshot: BoardSnapshot;
  readonly source: string;
}): ReactElement {
  const kinds = sourceKinds(snapshot.entries);
  const selected = kinds.includes(source) ? source : ALL_SOURCES;
  const shown = selectEntries(snapshot.entries, selected);
  const now = Date.now();
  return (
    <>
      <Chrome
        section="Board"
        counters={<Counters entries={shown} />}
        headerExtra={<SourceTabs tabs={tabsFor(snapshot.entries, kinds)} selected={selected} />}
      />
      <StageJump entries={shown} />
      <UnreadSources unresolved={unresolvedSources(snapshot.entries)} />
      <Rail entries={shown} now={now} />
      <div className="page">
        <div className="wrap">
          <RecordFoot
            readPath="/v1/board + /v1/tickets/{id}"
            watermark={`projection ${snapshot.health.toLowerCase()} · watermark ${snapshot.projectionWatermark.toString()} of ${snapshot.sourceWatermark.toString()} · columns are the record's lanes, project scoping lands with #185`}
          />
        </div>
      </div>
    </>
  );
}

function BoardFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Board" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Board</h1>
            <p>The portfolio ticket board, read from the instance record.</p>
          </div>
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Lanes</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath="/v1/board" />
        </div>
      </main>
    </>
  );
}

export default async function BoardPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const board = await recordAdapter.board();
  const source = readSource((await searchParams).source);
  return (
    <Resolved reading={board} frame={(declared) => <BoardFrame declared={declared} />}>
      {(snapshot) => <BoardBody snapshot={snapshot} source={source} />}
    </Resolved>
  );
}
