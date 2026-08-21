import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { configuredProjects, defaultProjectKey, selectedProjectKey } from "@/read/projects";
import { ProjectTabs } from "@/surfaces/board/ProjectTabs";
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
  ALL_LANES,
  ALL_SOURCES,
  countHeld,
  countInFlight,
  emptyTextFor,
  orderedForList,
  selectedLane,
  selectEntries,
  selectLanes,
  sourceKinds,
} from "@/surfaces/board/lanes";
import { BoardRail } from "@/surfaces/board/BoardRail";

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

/**
 * The cards, as one list.
 *
 * The record's lane is on every row and counted in the rail beside it; what is
 * gone is the column *layout*, and with it the pipeline claim that a card in one
 * column is on its way to the next. No read on this surface returns the workflow
 * that would make that claim true, and folding one out of the audit stream in
 * the browser is the projection this boundary does not get to hold.
 */
function List({
  entries,
  emptyText,
  now,
}: {
  readonly entries: readonly BoardEntry[];
  readonly emptyText: string;
  readonly now: number;
}): ReactElement {
  return (
    <div className="main">
      <div className="stack">
        {entries.map((entry) => (
          <LaneCard entry={entry} key={entry.card.ticketId} now={now} />
        ))}
      </div>
      {entries.length === 0 ? (
        <div className="col-empty" style={{ display: "block" }}>
          {emptyText}
        </div>
      ) : null}
    </div>
  );
}

function BoardBody({
  snapshot,
  source,
  lane,
  project,
  portfolioWatermark,
  portfolioEntries,
}: {
  readonly snapshot: BoardSnapshot;
  readonly source: string;
  readonly lane: string;
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
          headerExtra={
            <ProjectTabs projects={configuredProjects()} selected={project} lane={lane} />
          }
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
  const fromSource = selectEntries(snapshot.entries, selected);
  const selection = { project, source: selected, lane };
  const shown = orderedForList(selectLanes(fromSource, lane));
  const now = Date.now();
  return (
    <>
      {/* the project is the primary axis and sits in the header; source kind is
          provenance and filters *within* a project, one row down. The lane is a
          third narrowing and lives in the rail beside the list, where its counts
          are readable as an axis rather than as a pipeline */}
      <Chrome
        section="Board"
        counters={<Counters entries={shown} />}
        headerExtra={
          <>
            <ProjectTabs projects={configuredProjects()} selected={project} lane={lane} />
            <SourceTabs
              tabs={tabsFor(snapshot.entries, kinds)}
              selected={selected}
              selection={selection}
            />
          </>
        }
      />
      <UnreadSources unresolved={unresolvedSources(snapshot.entries)} />
      <main className="page">
        <div className="wrap">
          <div className="cols" style={{ paddingTop: "16px" }}>
            <List entries={shown} emptyText={emptyTextFor(lane)} now={now} />
            <BoardRail entries={fromSource} selection={selection} />
          </div>
          <RecordFoot
            readPath="/v1/board + /v1/tickets/{id}"
            watermark={`projection ${snapshot.health.toLowerCase()} · watermark ${snapshot.projectionWatermark.toString()} of ${snapshot.sourceWatermark.toString()} · one list, ordered by the recorded lane then priority · read with project_key=${snapshot.scope.projectKey}`}
          />
        </div>
      </main>
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
        headerExtra={
          <ProjectTabs projects={configuredProjects()} selected={project} lane={ALL_LANES} />
        }
      />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Board</h1>
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
  const lane = selectedLane(readParam(params, "lane"));
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
          lane={lane}
          project={project}
          portfolioWatermark={portfolioWatermark}
          portfolioEntries={portfolioEntries}
        />
      )}
    </Resolved>
  );
}
