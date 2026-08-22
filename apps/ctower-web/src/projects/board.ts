import type { BoardLane, BoardView, Priority } from "@ctower/client";
import type { MarkName } from "../ui/marks";

/**
 * What a project's board says about it, keyed over the closed sets the contract
 * declares rather than over the values one answer happened to carry.
 *
 * Every lane and every priority renders, at zero as readily as at three hundred:
 * a value the record may hold cannot arrive and draw nothing, and an operator
 * who never sees `blocked` cannot tell "no work is blocked" from "this screen
 * does not draw blocked work".
 */
export const LANES: readonly BoardLane[] = [
  "backlog",
  "ready",
  "in_progress",
  "in_review",
  "blocked",
  "complete",
];

export const PRIORITIES: readonly Priority[] = ["P0", "P1", "P2"];

export const LANE_WORD: Readonly<Record<BoardLane, string>> = {
  backlog: "backlog",
  ready: "ready",
  in_progress: "in progress",
  in_review: "in review",
  blocked: "blocked",
  complete: "complete",
};

/**
 * The lane's own state, in four of the six glyphs the CLI prints.
 *
 * Waiting is idle, both ends of a review are work moving, a blocker is parked
 * and not dead, and only `complete` is proven. No lane is ever `⛔`: a refusal
 * is something ctower said, and a lane is somewhere a ticket sits.
 */
export const LANE_MARK: Readonly<Record<BoardLane, MarkName>> = {
  backlog: "idle",
  ready: "idle",
  in_progress: "working",
  in_review: "working",
  blocked: "parked",
  complete: "done",
};

export function laneCount(view: BoardView, lane: BoardLane): number {
  return view.cards.filter((card) => card.lane === lane).length;
}

export function priorityCount(view: BoardView, priority: Priority): number {
  return view.cards.filter((card) => card.priority === priority).length;
}

/** Whether the projection this board was read from is current, in one word. */
export function healthWord(view: BoardView): string {
  return view.health === "CURRENT" ? "current" : "unknown";
}
