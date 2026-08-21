import { sourceKindOf } from "@/read/boardProjection";
import type { BoardEntry, BoardLane, Priority } from "@/read/interface";

/**
 * The lane vocabulary, in the record's own order.
 *
 * The approved mockup shows seven named pipeline stages. The shadow instance
 * does not record that vocabulary: its workflow is
 * `ctower.trust-spine-four-stage@1` and the fact every card carries is `lane`.
 * Rendering the mockup's stage names over lane data would have been an
 * invented mapping, so the lane identity follows the record.
 *
 * The Board no longer draws these as columns. A column board is a pipeline
 * claim — that a card in one column is on its way to the next — and the read
 * that would carry it does not exist yet (`operator-cockpit.md` §8.2 G10 for
 * the ticket read; the accepted design's slice 2 keeps this screen flat until
 * it lands). The lane is still every card's own recorded fact, so it stays: on
 * the card as a chip, and beside the list as a tally that filters. The
 * Portfolio still renders one column per entry, because there a lane is an
 * axis of counts rather than a pipeline the reader is invited to push work
 * along.
 */
export interface LaneColumn {
  readonly lane: BoardLane;
  readonly title: string;
  readonly bar: string;
  readonly anchor: string;
  readonly emptyText: string;
}

export const LANE_COLUMNS: readonly LaneColumn[] = [
  {
    lane: "backlog",
    title: "Backlog",
    bar: "b-intake",
    anchor: "lane-backlog",
    emptyText: "No backlog work from this source.",
  },
  {
    lane: "ready",
    title: "Ready",
    bar: "b-triage",
    anchor: "lane-ready",
    emptyText: "Nothing ready from this source.",
  },
  {
    lane: "in_progress",
    title: "In progress",
    bar: "b-build",
    anchor: "lane-in-progress",
    emptyText: "Nothing in progress from this source.",
  },
  {
    lane: "in_review",
    title: "In review",
    bar: "b-review",
    anchor: "lane-in-review",
    emptyText: "Nothing in review from this source.",
  },
  {
    lane: "blocked",
    title: "Blocked",
    bar: "b-qa",
    anchor: "lane-blocked",
    emptyText: "Nothing blocked from this source.",
  },
  {
    lane: "complete",
    title: "Complete",
    bar: "b-released",
    anchor: "lane-complete",
    emptyText: "Nothing complete from this source.",
  },
];

export const ALL_SOURCES = "all";
export const ALL_LANES = "all";

/** How a lane reads on a card, from the one table the two screens share. */
export function laneTitleOf(lane: BoardLane): string {
  return LANE_COLUMNS.find((column) => column.lane === lane)?.title ?? lane;
}

/** The lane the reader asked for, or `ALL_LANES` when they asked for none. */
export function selectedLane(requested: string | null): string {
  return LANE_COLUMNS.some((column) => column.lane === requested)
    ? (requested ?? ALL_LANES)
    : ALL_LANES;
}

const PRIORITIES: readonly Priority[] = ["P0", "P1", "P2"];

function rankOf(entry: BoardEntry): readonly [number, number] {
  const lane = LANE_COLUMNS.findIndex((column) => column.lane === entry.card.lane);
  const priority = PRIORITIES.indexOf(entry.card.priority);
  return [lane, priority];
}

/**
 * The flat list's order: recorded lane, then recorded priority, then the order
 * the projection answered in.
 *
 * Both keys are facts the card carries, and neither is a score — a card does
 * not move up this list for being older, busier or more likely to matter, and
 * nothing here ranks two cards the record ranks equally. The board says so in
 * its provenance foot, because an order is a claim about importance whether or
 * not a screen admits to making one.
 */
export function orderedForList(entries: readonly BoardEntry[]): readonly BoardEntry[] {
  return [...entries].sort((left, right) => {
    const [leftLane, leftPriority] = rankOf(left);
    const [rightLane, rightPriority] = rankOf(right);
    return leftLane - rightLane || leftPriority - rightPriority;
  });
}

export function sourceKinds(entries: readonly BoardEntry[]): readonly string[] {
  const kinds = new Set<string>();
  for (const entry of entries) {
    const kind = sourceKindOf(entry);
    if (kind !== null) {
      kinds.add(kind);
    }
  }
  return [...kinds].sort((left, right) => left.localeCompare(right));
}

export function selectEntries(
  entries: readonly BoardEntry[],
  source: string
): readonly BoardEntry[] {
  if (source === ALL_SOURCES) {
    return entries;
  }
  return entries.filter((entry) => sourceKindOf(entry) === source);
}

export function inLane(entries: readonly BoardEntry[], lane: BoardLane): readonly BoardEntry[] {
  return entries.filter((entry) => entry.card.lane === lane);
}

/**
 * What an empty list says, in the words of the lane the reader asked for. The
 * source is named too: an empty answer under a filter is a fact about the
 * filter, and reading it as an empty board is the mistake this surface guards
 * everywhere else.
 */
export function emptyTextFor(lane: string): string {
  return (
    LANE_COLUMNS.find((column) => column.lane === lane)?.emptyText ?? "No cards from this source."
  );
}

/** The same filter for the URL's value, which may be every lane. */
export function selectLanes(entries: readonly BoardEntry[], lane: string): readonly BoardEntry[] {
  return lane === ALL_LANES ? entries : entries.filter((entry) => entry.card.lane === lane);
}

export function countInFlight(entries: readonly BoardEntry[]): number {
  return entries.filter(
    (entry) => entry.card.lane === "in_progress" || entry.card.lane === "in_review"
  ).length;
}

/** Cards whose board row carries a recorded workflow stage. */
export function countStaged(entries: readonly BoardEntry[]): number {
  return entries.filter((entry) => entry.card.stageLabel !== null).length;
}

export function countHeld(entries: readonly BoardEntry[]): number {
  return entries.filter(
    (entry) => entry.card.lane === "blocked" || entry.card.blockerReason !== null
  ).length;
}
