import Link from "next/link";
import type { CSSProperties, ReactElement } from "react";
import { KnownAbsence } from "@/frame/Declared";
import { LANE_COLUMNS } from "@/surfaces/board/lanes";
import type { BoardLane, Portfolio, PortfolioLane, PortfolioProject } from "@/read/interface";

/**
 * Projects down, the record's lanes across.
 *
 * The columns are `lane`, not the mockup's pipeline stage names, for the reason
 * the Board already states: the shadow instance runs a four-stage workflow and
 * `lane` is the fact every card carries, so a stage axis here would be an
 * invented mapping over lane data. The column identity is the Board's own
 * `LANE_COLUMNS`, so the two screens cannot drift into different columns.
 *
 * The row worth reading the code for is the project whose board did not answer.
 * It does not draw six dashes across the lane cells — six dashes read as six
 * zeroes, which is the claim *this project has no work*. It draws one cell
 * spanning the lanes carrying the shared not-reached treatment, and the totals
 * row beneath counts only the boards that answered.
 *
 * `all` sits second, immediately after the project, rather than last. The grid
 * is wider than a phone and scrolls inside its own panel there; with the total
 * last, the render at 375 showed `manibo 89 ·` and hid the one number the sweep
 * is for. Reading order is now the project, how much it holds, then where that
 * work sits — and the columns that scroll away are the ones a reader can afford
 * to scroll to.
 */

const LABEL_COLUMN = 150;
const LANE_MIN = 58;
const LANE_MAX = 78;
const TOTAL_MIN = 46;
const TOTAL_MAX = 58;

const COLUMNS: CSSProperties = {
  gridTemplateColumns: `minmax(${LABEL_COLUMN.toString()}px, 1fr) minmax(${TOTAL_MIN.toString()}px, ${TOTAL_MAX.toString()}px) repeat(${LANE_COLUMNS.length.toString()}, minmax(${LANE_MIN.toString()}px, ${LANE_MAX.toString()}px))`,
  minWidth: `${(LABEL_COLUMN + TOTAL_MAX + LANE_COLUMNS.length * LANE_MAX).toString()}px`,
};

function countIn(lanes: readonly PortfolioLane[], lane: BoardLane): number {
  return lanes.find((entry) => entry.lane === lane)?.count ?? 0;
}

function Head(): ReactElement {
  return (
    <div className="org-head" style={COLUMNS}>
      <span>Project</span>
      <span className="t">all</span>
      {LANE_COLUMNS.map((column) => (
        <span key={column.lane} title={column.title}>
          {column.title}
        </span>
      ))}
    </div>
  );
}

function Row({ project }: { readonly project: PortfolioProject }): ReactElement {
  const counts = project.counts;
  return (
    <Link className="org-row" href={project.boardHref} style={COLUMNS}>
      <span className="s">
        <i className="av">{project.key.slice(0, 2).toUpperCase()}</i>
        <span className="nm">{project.key}</span>
      </span>
      {counts.known === "value" ? (
        <>
          <span className={counts.value.tickets === 0 ? "c t" : "c t on"}>
            {counts.value.tickets}
          </span>
          {LANE_COLUMNS.map((column) => {
            const count = countIn(counts.value.lanes, column.lane);
            return (
              <span className={count === 0 ? "c" : "c on"} key={column.lane}>
                {count === 0 ? "·" : count}
              </span>
            );
          })}
        </>
      ) : (
        <span
          className="c t"
          style={{ gridColumn: "2 / -1", textAlign: "left", overflowWrap: "anywhere" }}
        >
          <KnownAbsence value={counts} />
        </span>
      )}
    </Link>
  );
}

function Totals({ portfolio }: { readonly portfolio: Portfolio }): ReactElement {
  return (
    <div className="org-row" style={{ ...COLUMNS, background: "var(--surface)" }}>
      <span
        className="s"
        style={{
          color: "var(--ink-3)",
          fontSize: "11px",
          letterSpacing: ".06em",
          textTransform: "uppercase",
        }}
      >
        Portfolio
      </span>
      <span className="c t on">{portfolio.tickets}</span>
      {LANE_COLUMNS.map((column) => (
        <span className="c on" key={column.lane}>
          {countIn(portfolio.laneTotals, column.lane)}
        </span>
      ))}
    </div>
  );
}

export function ProjectLanes({ portfolio }: { readonly portfolio: Portfolio }): ReactElement {
  return (
    // the fleet decides how many projects there are and the record decides how
    // many lanes; on a phone the grid scrolls inside its own panel rather than
    // crushing the project names or pushing the page sideways
    <div className="org" style={{ overflowX: "auto" }}>
      <Head />
      {portfolio.projects.map((project) => (
        <Row key={project.key} project={project} />
      ))}
      <Totals portfolio={portfolio} />
    </div>
  );
}
