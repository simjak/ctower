import type { BoardCard, BoardLane, BoardView, CompanyBundleDocument } from "@ctower/client";

/**
 * The board's axis, and where every word on it comes from.
 *
 * The six lanes are the contract's own closed `BoardLane` set, in the order
 * work moves through them. The column is not a stage: a card carries the
 * workflow position it declares in `stage_key`, and a card that declares none
 * gets none drawn. Nothing here derives a position, groups by a guess, or
 * invents a seventh column for the cards that answer nothing.
 */
export const LANES: readonly BoardLane[] = [
  "backlog",
  "ready",
  "in_progress",
  "in_review",
  "blocked",
  "complete",
];

/**
 * The operator's word for each lane. These are states a person says out loud,
 * not operations: `in_progress` is the record's spelling of "In progress" and
 * the screen says the second one.
 */
export function laneLabel(lane: BoardLane): string {
  return LANE_LABEL[lane];
}

const LANE_LABEL: Readonly<Record<BoardLane, string>> = {
  backlog: "Backlog",
  ready: "Ready",
  in_progress: "In progress",
  in_review: "In review",
  blocked: "Blocked",
  complete: "Complete",
};

export interface Column {
  readonly lane: BoardLane;
  readonly label: string;
  readonly cards: readonly BoardCard[];
}

/** The six columns, in lane order, each holding the cards that declare it. */
export function columnsOf(cards: readonly BoardCard[]): readonly Column[] {
  return LANES.map((lane) => ({
    lane,
    label: laneLabel(lane),
    cards: cards.filter((card) => card.lane === lane),
  }));
}

/**
 * How far behind the read is.
 *
 * A board is a projection, and a projection folds after the command it
 * describes is durable. `STATE_UNKNOWN` is not "current" and is never drawn as
 * one; a projection that has not caught up says so rather than presenting a
 * stale count as the truth. The two watermarks are record positions, so their
 * difference is not a number of tickets and is never rendered as one.
 */
export type Freshness =
  | { readonly kind: "current" }
  | { readonly kind: "behind"; readonly detail: string }
  | { readonly kind: "unknown" };

export function freshnessOf(view: BoardView): Freshness {
  if (view.health === "STATE_UNKNOWN") {
    return { kind: "unknown" };
  }
  if (view.projection_watermark < view.source_watermark) {
    return {
      kind: "behind",
      detail: `folded to ${String(view.projection_watermark)} of ${String(view.source_watermark)}`,
    };
  }
  return { kind: "current" };
}

export interface Project {
  /** The work-plane key the board is read by. */
  readonly key: string;
  /** The name the definition gives it. */
  readonly name: string;
}

/**
 * The projects this company's definition names, and how a definition key
 * becomes a board key.
 *
 * They are not the same string: the board reads `ctower`, the definition holds
 * `ctower.control-plane`. The record itself owns the rule that joins them —
 * `allocate_ticket_display_key` matches a project component by
 * `split_part(component_key, '.', 1)` — so the first segment is read here and
 * nothing is guessed. ctower has no operation that enumerates work-plane
 * projects, so this is what the definition knows, never a closed list.
 */
export function projectsOf(document: CompanyBundleDocument): readonly Project[] {
  const found = new Map<string, string>();
  for (const resource of document.resources) {
    if (resource.component.kind !== "project") {
      continue;
    }
    const key = resource.component.key.split(".")[0];
    const name = resource.payload.display_name;
    if (key !== undefined && key !== "" && !found.has(key)) {
      found.set(key, typeof name === "string" && name !== "" ? name : key);
    }
  }
  return [...found]
    .map(([key, name]) => ({ key, name }))
    .sort((left, right) => left.key.localeCompare(right.key));
}
