import type { BoardEntry, BoardLane } from "@/read/interface";

/**
 * The board's columns are the record's own lanes.
 *
 * The approved mockup shows seven named pipeline stages. The shadow instance
 * does not record that vocabulary: its workflow is
 * `ctower.trust-spine-four-stage@1` and the fact every card carries is `lane`.
 * Rendering the mockup's stage names over lane data would have been an
 * invented mapping, so the column identity follows the record and the layout,
 * ramp and card shape follow the mockup exactly.
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

export function sourceKindOf(entry: BoardEntry): string | null {
  return entry.ticket?.source.kind ?? null;
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

export function countInFlight(entries: readonly BoardEntry[]): number {
  return entries.filter(
    (entry) => entry.card.lane === "in_progress" || entry.card.lane === "in_review"
  ).length;
}

export function countHeld(entries: readonly BoardEntry[]): number {
  return entries.filter(
    (entry) => entry.card.lane === "blocked" || entry.card.blockerReason !== null
  ).length;
}
