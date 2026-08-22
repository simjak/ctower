import type {
  BoardCard,
  BoardLane,
  BoardView,
  CompanyBundleDocument,
  Priority,
} from "@ctower/client";

/**
 * The board's axis, and the words on it.
 *
 * The six lanes are the contract's own closed set, in the order work moves
 * through them. A lane is not a stage: a card carries the workflow position it
 * declares in `stage_label`, and one that declares none is drawn without one.
 * Nothing here derives a position or invents a column for the cards that answer
 * nothing.
 */
export const LANES: readonly BoardLane[] = [
  "backlog",
  "ready",
  "in_progress",
  "in_review",
  "blocked",
  "complete",
];

const LANE_LABEL: Readonly<Record<BoardLane, string>> = {
  backlog: "Backlog",
  ready: "Ready",
  in_progress: "In progress",
  in_review: "In review",
  blocked: "Blocked",
  complete: "Complete",
};

export function laneLabel(lane: BoardLane): string {
  return LANE_LABEL[lane];
}

export interface Column {
  readonly lane: BoardLane;
  readonly label: string;
  readonly cards: readonly BoardCard[];
}

export function columnsOf(cards: readonly BoardCard[]): readonly Column[] {
  return LANES.map((lane) => ({
    lane,
    label: LANE_LABEL[lane],
    cards: cards.filter((card) => card.lane === lane),
  }));
}

/** The priority filter's own vocabulary: the contract's three, or none of them. */
export type PriorityChoice = Priority | "any";

export const PRIORITIES: readonly PriorityChoice[] = ["any", "P0", "P1", "P2"];

/**
 * The priority filter narrows what was answered; it does not re-ask.
 *
 * `getBoard` carries a priority parameter, so this could have been a second
 * read. It is not: the board is one projection answered at one watermark, and
 * narrowing it in the browser keeps every card the operator compares on the same
 * fold. A re-read would silently mix two watermarks in one glance.
 */
export function atPriority(
  cards: readonly BoardCard[],
  choice: PriorityChoice
): readonly BoardCard[] {
  return choice === "any" ? cards : cards.filter((card) => card.priority === choice);
}

/**
 * How far behind the read is.
 *
 * A board is a projection and folds after the command it describes is durable.
 * `STATE_UNKNOWN` is not "current" and is never drawn as one. The two watermarks
 * are record positions, so their difference is not a number of tickets and is
 * never rendered as one.
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
  /** The name the company definition gives it. */
  readonly name: string;
}

/**
 * The projects this company's definition names, and how a definition key becomes
 * a board key.
 *
 * They are not the same string: the board reads `ctower`, the definition holds
 * `ctower.control-plane`. The record owns the rule that joins them —
 * `allocate_ticket_display_key` matches a project component by its key's first
 * dot-segment — so that segment is read here and nothing is guessed.
 */
export function projectsOf(document: CompanyBundleDocument): readonly Project[] {
  const found = new Map<string, string>();
  for (const resource of document.resources) {
    if (resource.component.kind !== "project") {
      continue;
    }
    const key = resource.component.key.split(".")[0] ?? "";
    const name = resource.payload.display_name;
    if (key !== "" && !found.has(key)) {
      found.set(key, typeof name === "string" && name !== "" ? name : key);
    }
  }
  return [...found]
    .map(([key, name]) => ({ key, name }))
    .sort((left, right) => left.key.localeCompare(right.key));
}
