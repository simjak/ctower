import type { BoardLane, Priority } from "@ctower/client";

/**
 * The tickets the T-028 bench draws with, and the two shapes it draws them in.
 *
 * Fixtures, and they say so. Every field below is one the board read actually
 * answers with — the lane, the priority, the title, the number, the workflow
 * position, the blocker and whether a person is being waited on — so a screen
 * built on this data is a screen a live tower can fill.
 *
 * Two fields are the exception, and they are the whole question this bench puts
 * to the operator: `face` is the name his reference draws on a card, which no
 * read this console can make will answer; and `cancelled` is a column his
 * reference keeps, which the record has no lane for. Both are drawn here so he
 * can rule on pixels rather than on a paragraph.
 */

/** The reference's seventh column, in a type that says the record has no such lane. */
export type MockLane = BoardLane | "cancelled";

export interface MockCard {
  /** The number a person says out loud; `null` until the record allocates one. */
  readonly key: string | null;
  readonly title: string;
  readonly lane: MockLane;
  readonly priority: Priority;
  /** The workflow position the card declares, as a word; `null` when it declares none. */
  readonly stage: string | null;
  /** Whether a finding on it is waiting on a person. */
  readonly waiting: boolean;
  /** The blocker the record opened, in the words a person wrote. */
  readonly blocked: string | null;
  /**
   * The name the reference puts on a card. The record answers who with an
   * identifier and nothing turns one into a name, so this is the one invented
   * value on the bench and it is drawn only in the reference shape.
   */
  readonly face: string;
}

export const CARDS: readonly MockCard[] = [
  {
    key: "CTW-34",
    title: "The morning digest lands before the first stand-up",
    lane: "backlog",
    priority: "P2",
    stage: null,
    waiting: false,
    blocked: null,
    face: "Ada",
  },
  {
    key: "CTW-33",
    title: "The cockpit's panes say so when the window cannot hold them",
    lane: "backlog",
    priority: "P2",
    stage: null,
    waiting: false,
    blocked: null,
    face: "Luna",
  },
  {
    key: null,
    title: "One place to see what every crew is doing right now",
    lane: "backlog",
    priority: "P2",
    stage: null,
    waiting: false,
    blocked: null,
    face: "Ox",
  },
  {
    key: "CTW-32",
    title: "The nightly recheck runs itself and says what it found",
    lane: "ready",
    priority: "P1",
    stage: null,
    waiting: false,
    blocked: null,
    face: "Sol",
  },
  {
    key: "CTW-26",
    title: "The company page says what it is, not what addresses it",
    lane: "ready",
    priority: "P1",
    stage: null,
    waiting: false,
    blocked: null,
    face: "Vela",
  },
  {
    key: "CTW-35",
    title: "The Board reads as columns, in the words you use",
    lane: "in_progress",
    priority: "P1",
    stage: "In design",
    waiting: true,
    blocked: null,
    face: "Ada",
  },
  {
    key: "CTW-31",
    title: "The Tickets page, laid down first",
    lane: "in_progress",
    priority: "P1",
    stage: "Build",
    waiting: false,
    blocked: null,
    face: "Luna",
  },
  {
    key: "CTW-20",
    title: "A ticket keeps the whole conversation, not the last line of it",
    lane: "in_progress",
    priority: "P2",
    stage: "Build",
    waiting: false,
    blocked: null,
    face: "Juno",
  },
  {
    key: "CTW-29",
    title: "The harness is a card and an agent is a person",
    lane: "in_review",
    priority: "P1",
    stage: "Review",
    waiting: false,
    blocked: null,
    face: "Ox",
  },
  {
    key: "CTW-28",
    title: "The walk asserts a job, not a page",
    lane: "in_review",
    priority: "P2",
    stage: "Review",
    waiting: false,
    blocked: null,
    face: "Sol",
  },
  {
    key: "CTW-27",
    title: "A project key with a dot is refused at the door",
    lane: "blocked",
    priority: "P0",
    stage: "Build",
    waiting: false,
    blocked: "Waiting on you to say whether a dotted key is kept.",
    face: "Vela",
  },
  {
    key: "CTW-22",
    title: "The routine items stop failing on the turn of a minute",
    lane: "blocked",
    priority: "P1",
    stage: "Recheck",
    waiting: true,
    blocked: "The recheck host has no browser to run the walk on.",
    face: "Rhea",
  },
  {
    key: "CTW-30",
    title: "The rail is two workspaces, and a project is a scope",
    lane: "complete",
    priority: "P1",
    stage: "Live",
    waiting: false,
    blocked: null,
    face: "Luna",
  },
  {
    key: "CTW-25",
    title: "The staff are in the rail, by name",
    lane: "complete",
    priority: "P1",
    stage: "Live",
    waiting: false,
    blocked: null,
    face: "Ada",
  },
  {
    key: "CTW-24",
    title: "A project is made in a pop-up, and its number comes from its name",
    lane: "complete",
    priority: "P2",
    stage: "Live",
    waiting: false,
    blocked: null,
    face: "Ox",
  },
  {
    key: "CTW-18",
    title: "The weekly summary goes out to the whole company by email",
    lane: "cancelled",
    priority: "P2",
    stage: null,
    waiting: false,
    blocked: null,
    face: "Sol",
  },
  {
    key: "CTW-12",
    title: "The console is rewritten on a second framework",
    lane: "cancelled",
    priority: "P2",
    stage: null,
    waiting: false,
    blocked: null,
    face: "Juno",
  },
];

/**
 * The lane words, and they are the operator's rather than the record's.
 *
 * T-027 froze this vocabulary on the ticket screens; a board is the same
 * tickets read as columns, so it says the same words. `cancelled` has no
 * recorded lane behind it and is drawn only in the reference shape.
 */
const WORD: Readonly<Record<MockLane, string>> = {
  backlog: "Waiting",
  ready: "Ready to start",
  in_progress: "Being worked on",
  in_review: "In review",
  blocked: "Stuck",
  complete: "Done",
  cancelled: "Cancelled",
};

export function laneName(lane: MockLane): string {
  return WORD[lane];
}

/** The six the record keeps, in the order work moves through them. */
export const RECORDED_LANES: readonly MockLane[] = [
  "backlog",
  "ready",
  "in_progress",
  "in_review",
  "blocked",
  "complete",
];

/** The seven his kanban reference draws. */
export const REFERENCE_LANES: readonly MockLane[] = [...RECORDED_LANES, "cancelled"];

export function heldIn(lane: MockLane): readonly MockCard[] {
  return CARDS.filter((card) => card.lane === lane);
}

/** What the head says about the board: what is open, and what wants a person. */
export function standing(lanes: readonly MockLane[]): string {
  const shown = CARDS.filter((card) => lanes.includes(card.lane));
  const open = shown.filter((card) => card.lane !== "complete" && card.lane !== "cancelled");
  const waiting = shown.filter((card) => card.waiting).length;
  const stuck = shown.filter((card) => card.lane === "blocked").length;
  return `${String(open.length)} open · ${String(waiting)} need you · ${String(stuck)} stuck`;
}

export interface MockProject {
  readonly key: string;
  readonly name: string;
  readonly prefix: string;
}

/** The projects this company records; the switcher offers exactly these. */
export const PROJECTS: readonly MockProject[] = [
  { key: "ctower", name: "ctower", prefix: "CTW" },
  { key: "mission-control", name: "Mission control", prefix: "MC" },
];

export const HERE: MockProject = PROJECTS[0] ?? { key: "ctower", name: "ctower", prefix: "CTW" };

export const COMPANY = "Manibo";

/** The staff this company records, by the names their own components carry. */
export const STAFF: readonly string[] = ["Ada", "Luna", "Ox", "Sol", "Vela", "Juno", "Rhea"];
