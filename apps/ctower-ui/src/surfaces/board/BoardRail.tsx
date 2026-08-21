import Link from "next/link";
import type { ReactElement } from "react";
import { NoSourceYet } from "@/frame/Declared";
import { laneGlyph, StateGlyph } from "@/frame/StateGlyph";
import { NO_CHANGE_SIZE, NO_STAGES_HERE, NO_TICKET_INVENTORY } from "@/read/futureSources";
import type { BoardEntry } from "@/read/interface";
import { Count } from "@/surfaces/Count";
import { boardHref } from "./boardHref";
import type { BoardSelection } from "./boardHref";
import { ALL_LANES, countStaged, inLane, LANE_COLUMNS } from "./lanes";

const ROW = {
  display: "flex",
  alignItems: "center",
  gap: "9px",
  width: "100%",
  minWidth: 0,
} as const;

function LaneRow({
  href,
  glyph,
  label,
  count,
  current,
}: {
  readonly href: string;
  readonly glyph: ReactElement;
  readonly label: string;
  readonly count: number;
  readonly current: boolean;
}): ReactElement {
  return (
    <li>
      <Link
        className="v"
        href={href}
        aria-current={current ? "page" : undefined}
        style={{ ...ROW, color: current ? "var(--ink)" : undefined }}
      >
        {glyph}
        {label}
        <span style={{ marginLeft: "auto" }}>
          <Count value={count} unit={count === 1 ? "card" : "cards"} />
        </span>
      </Link>
    </li>
  );
}

/**
 * The lane axis, beside the list rather than under it.
 *
 * This is what the column board was for, and all it could honestly claim: how
 * much work sits in each recorded lane, and a way to see one lane's worth of it.
 * As columns the same six facts read as a pipeline — that a card in one column
 * is on its way to the next — which is a claim about a workflow no read on this
 * surface returns.
 */
function Lanes({
  entries,
  selection,
}: {
  readonly entries: readonly BoardEntry[];
  readonly selection: BoardSelection;
}): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>Lanes</h2>
      </header>
      <ul className="links">
        {/* no mark on this row: "every lane" is not a state the record holds,
            and lending it one of the six would say that it is */}
        <LaneRow
          href={boardHref({ ...selection, lane: ALL_LANES })}
          glyph={<span aria-hidden style={{ width: "13px", flex: "none" }} />}
          label="Every lane"
          count={entries.length}
          current={selection.lane === ALL_LANES}
        />
        {LANE_COLUMNS.map((column) => (
          <LaneRow
            key={column.lane}
            href={boardHref({ ...selection, lane: column.lane })}
            glyph={<StateGlyph name={laneGlyph(column.lane, false)} />}
            label={column.title}
            count={inLane(entries, column.lane).length}
            current={selection.lane === column.lane}
          />
        ))}
      </ul>
    </section>
  );
}

/**
 * The workflow stage, counted rather than repeated.
 *
 * `/v1/board` does carry `stage_key` and `stage_label` per card — the gap the
 * design records is on the *ticket* read, and it is narrower than a reader of
 * that gap list would expect. Most cards carry no stage, so the absence is
 * declared once here with its measurement instead of printing on every row: an
 * honest sentence repeated three hundred times is read no more carefully than a
 * dishonest one.
 */
function Stage({ entries }: { readonly entries: readonly BoardEntry[] }): ReactElement {
  const staged = countStaged(entries);
  return (
    <section className="panel">
      <header>
        <h2>Stage</h2>
      </header>
      {staged === 0 ? (
        <NoSourceYet brief source={NO_STAGES_HERE} />
      ) : (
        <ul className="links">
          <li>
            <span className="k">recorded</span>
            <span className="v">
              <Count
                value={staged}
                unit={staged === 1 ? "card" : "cards"}
                detail="cards whose board row carries a workflow stage"
              />
            </span>
          </li>
          <li>
            <span className="k">no stage</span>
            <span className="v">
              <Count
                value={entries.length - staged}
                unit="cards"
                detail="the record carries a stage for these and holds none"
              />
            </span>
          </li>
        </ul>
      )}
    </section>
  );
}

/**
 * What this screen cannot answer, said where the reader is standing.
 *
 * Both are absences of a *read*, not of a fact the operator could go and find
 * somewhere else on this surface — which is exactly why they belong on the
 * screen that looks like it should have them.
 */
function Unserved(): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>Not on this read</h2>
      </header>
      <NoSourceYet brief source={NO_CHANGE_SIZE} />
      <NoSourceYet brief source={NO_TICKET_INVENTORY} />
    </section>
  );
}

export function BoardRail({
  entries,
  shown,
  selection,
}: {
  /** The cards the source filter admits, before the lane filter narrows them:
      the lane tally has to count the lanes the reader is not standing in. */
  readonly entries: readonly BoardEntry[];
  /** The cards actually listed beside this rail. The stage tally counts these,
      so two numbers a few pixels apart never turn out to be counting two
      different sets of cards. */
  readonly shown: readonly BoardEntry[];
  readonly selection: BoardSelection;
}): ReactElement {
  return (
    <aside className="rail-r" style={{ gridColumn: 2, gridRow: 1 }}>
      <Lanes entries={entries} selection={selection} />
      <Stage entries={shown} />
      <Unserved />
    </aside>
  );
}
