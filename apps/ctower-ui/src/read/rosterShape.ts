import { initialsOf, seatLabelOf } from "./sources/crewNaming";
import type { Known } from "./sources/maybe";
import type { CrewRow, ModelShare, ProjectRoster, RosterFilter, SeatRow } from "./interface";

/**
 * How live crew rows become the roster the Org screen draws: a seats-by-projects
 * grid, the per-project groups beneath it, and the filter chips above it.
 *
 * Pure shaping, and deliberately source-free — which is why it sits beside
 * `sources/` rather than inside it. It is handed rows and the
 * declared seat list, and knows nothing about tmux, the crew log or the personas
 * directory. That is what lets the grid's arithmetic be checked in isolation,
 * and it is why every count here is derived from the rows themselves. The screen
 * prints no number this module did not count from what it is about to show.
 */

const NOT_RECORDED = "project not recorded";

export function projectKeyOf(row: CrewRow): string {
  return row.project.known === "value" ? row.project.value : NOT_RECORDED;
}

export function groupsOf(rows: readonly CrewRow[]): readonly ProjectRoster[] {
  const keys = [...new Set(rows.map(projectKeyOf))].sort((left, right) => {
    if (left === NOT_RECORDED) {
      return 1;
    }
    if (right === NOT_RECORDED) {
      return -1;
    }
    return left.localeCompare(right);
  });
  return keys.map((key): ProjectRoster => {
    const crews = rows.filter((row) => projectKeyOf(row) === key);
    return {
      key,
      label: key,
      crews,
      inFlight: crews.filter((row) => row.activity === "in-flight").length,
      parked: crews.filter((row) => row.activity === "parked").length,
      held: crews.filter((row) => row.activity === "held").length,
    };
  });
}

export function seatRowsOf(
  rows: readonly CrewRow[],
  seats: Known<readonly string[]>,
  columns: readonly string[]
): readonly SeatRow[] {
  const declared = seats.known === "value" ? seats.value : [];
  return declared.map((seat): SeatRow => {
    const mine = rows.filter((row) => row.seat.known === "value" && row.seat.value === seat);
    return {
      seat,
      label: seatLabelOf(seat),
      initials: initialsOf(seat),
      perProject: columns.map(
        (column) => mine.filter((row) => projectKeyOf(row) === column).length
      ),
      total: mine.length,
    };
  });
}

export function modelsOf(rows: readonly CrewRow[]): readonly ModelShare[] {
  const counts = new Map<string, { harness: Known<string>; count: number }>();
  for (const row of rows) {
    const label = row.model.known === "value" ? row.model.value : "model not recorded";
    const current = counts.get(label);
    counts.set(label, { harness: row.harness, count: (current?.count ?? 0) + 1 });
  }
  return [...counts.entries()]
    .map(([label, entry]): ModelShare => ({ label, harness: entry.harness, count: entry.count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

export function filtersOf(
  rows: readonly CrewRow[],
  of: (row: CrewRow) => string | null
): RosterFilter[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const key = of(row);
    if (key !== null) {
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([key, count]): RosterFilter => ({ key, label: key, count }))
    .sort((left, right) => right.count - left.count || left.key.localeCompare(right.key));
}
