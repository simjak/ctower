import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { configuredProjects, defaultProjectKey, selectedProjectKey } from "@/read/projects";
import { ProjectTabs } from "@/surfaces/board/ProjectTabs";
import { ScopeNote } from "@/surfaces/board/ScopeNote";
import { StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter } from "@/read/adapter";
import {
  boardEmptyKind,
  portfolioEntriesFor,
  portfolioWatermarkFor,
  sourceKindOf,
  unresolvedSources,
} from "@/read/boardProjection";
import type { BoardEntry, BoardSnapshot, Reading } from "@/read/interface";
import { LaneCard } from "@/surfaces/board/LaneCard";
import { SourceTabs } from "@/surfaces/board/SourceTabs";
import { TrueEmptyProject } from "@/surfaces/board/TrueEmptyProject";
import { UnreadSources } from "@/surfaces/board/UnreadSources";
import { ZeroOfZeroRefusal } from "@/surfaces/board/ZeroOfZeroRefusal";
import { readParam } from "@/surfaces/screenParams";
import { Count } from "@/surfaces/Count";
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
      {/* a glyph is not a label: each counter says what it counts (#239) */}
      <span className="ctr c-flight">
        <StateGlyph name="flight" />
        <Count value={countInFlight(entries)} unit="in flight" />
      </span>
      <span className="ctr c-held">
        <StateGlyph name="held" />
        <Count value={countHeld(entries)} unit="held" />
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
          <Count value={inLane(entries, column.lane).length} unit="cards" />
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
  project,
  portfolioWatermark,
  portfolioEntries,
}: {
  readonly snapshot: BoardSnapshot;
  readonly source: string;
  readonly project: string;
  /** The unbounded board's projection watermark read in the same render, or
      null when that read did not answer. Only set for a 0-of-0 scoped answer. */
  readonly portfolioWatermark: number | null;
  /** The unbounded board's own entries, read in the same render as
      `portfolioWatermark`. Empty except for a true-empty-project answer. */
  readonly portfolioEntries: readonly BoardEntry[];
}): ReactElement {
  /* A board that answers watermark 0 of 0 with zero cards is never rendered as
     a normal empty board: it is either a restarting/fresh instance (portfolio
     also 0) or a genuinely not-yet-imported project (portfolio nonzero). Each
     gets its own named block. Any watermark > 0 — a genuinely empty PROJECT
     under a nonzero watermark included — and any board with cards renders
     normally below. Every project tab and the unscoped (default) board pass
     through this single body, so one guard covers them all. */
  const kind = boardEmptyKind({
    projectionWatermark: snapshot.projectionWatermark,
    entries: snapshot.entries,
    portfolioWatermark,
  });
  if (kind === "restart-fresh" || kind === "true-empty-project") {
    return (
      <>
        <Chrome
          section="Board"
          headerExtra={<ProjectTabs projects={configuredProjects()} selected={project} />}
        />
        {kind === "restart-fresh" ? (
          <ZeroOfZeroRefusal project={project} snapshot={snapshot} />
        ) : (
          <TrueEmptyProject project={project} portfolioEntries={portfolioEntries} />
        )}
        <div className="page">
          <div className="wrap">
            <RecordFoot readPath="/v1/board" />
          </div>
        </div>
      </>
    );
  }
  const kinds = sourceKinds(snapshot.entries);
  const selected = kinds.includes(source) ? source : ALL_SOURCES;
  const shown = selectEntries(snapshot.entries, selected);
  const now = Date.now();
  return (
    <>
      {/* the project is the primary axis and sits in the header; source kind is
          provenance and filters *within* a project, one row down */}
      <Chrome
        section="Board"
        counters={<Counters entries={shown} />}
        headerExtra={
          <>
            <ProjectTabs projects={configuredProjects()} selected={project} />
            <SourceTabs tabs={tabsFor(snapshot.entries, kinds)} selected={selected} />
          </>
        }
      />
      <ScopeNote scope={snapshot.scope} />
      <StageJump entries={shown} />
      <UnreadSources unresolved={unresolvedSources(snapshot.entries)} />
      <Rail entries={shown} now={now} />
      <div className="page">
        <div className="wrap">
          <RecordFoot
            readPath="/v1/board + /v1/tickets/{id}"
            watermark={`projection ${snapshot.health.toLowerCase()} · watermark ${snapshot.projectionWatermark.toString()} of ${snapshot.sourceWatermark.toString()} · columns are the record's lanes · read with project_key=${snapshot.scope.projectKey}`}
          />
        </div>
      </div>
    </>
  );
}

function BoardFrame({
  declared,
  project,
}: {
  readonly declared: ReactElement;
  readonly project: string;
}): ReactElement {
  return (
    <>
      <Chrome
        section="Board"
        headerExtra={<ProjectTabs projects={configuredProjects()} selected={project} />}
      />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Board</h1>
            <p>The ticket board for {project}, read from the instance record.</p>
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
  const params = await searchParams;
  const project = selectedProjectKey(readParam(params, "project"));
  const board = await recordAdapter.board(project);
  const source = readSource(params.source);
  /* Only a 0-of-0 scoped answer needs the portfolio watermark to tell a
     true-empty project (import has not run, portfolio nonzero) from a
     restarting/fresh instance (portfolio also 0). The read is lazy and lives
     in the read layer: a normal board (watermark > 0, or cards) never pays for
     a second read, and the surface never inspects a Reading's state directly.
     The page is force-dynamic, so no answer is cached across renders: a
     refusal is never served stale from an earlier board.

     `readPortfolio` is memoized so the true-empty-project case, which needs
     both the portfolio's watermark AND its entries (gh#319 direction-a's
     cross-project view), pays for exactly one extra read, not two. */
  let portfolioReading: Promise<Reading<BoardSnapshot>> | null = null;
  const readPortfolio = (): Promise<Reading<BoardSnapshot>> => {
    portfolioReading ??= recordAdapter.board(defaultProjectKey());
    return portfolioReading;
  };
  const portfolioWatermark = await portfolioWatermarkFor(board, readPortfolio);
  const portfolioEntries = await portfolioEntriesFor(readPortfolio, portfolioWatermark);
  return (
    <Resolved
      reading={board}
      subject={`project ${project}`}
      frame={(declared) => <BoardFrame declared={declared} project={project} />}
    >
      {(snapshot) => (
        <BoardBody
          snapshot={snapshot}
          source={source}
          project={project}
          portfolioWatermark={portfolioWatermark}
          portfolioEntries={portfolioEntries}
        />
      )}
    </Resolved>
  );
}
