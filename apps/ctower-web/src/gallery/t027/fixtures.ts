import type { BoardLane, Priority } from "@ctower/client";

/**
 * The tickets the T-027 bench draws with.
 *
 * Fixtures, and they say so. Every field below is one the authored contract
 * actually answers with, so a screen built on this data is a screen a live
 * tower can fill: `lane`, `priority`, `title` and the ticket's own number come
 * from the board read, `raisedAt` from the project's own event read, the
 * blocker and the waiting mark from the two facts a card carries about being
 * stopped.
 *
 * One field the reference has is missing on purpose. Who a ticket is *for* is
 * answered by the record as an identifier and by nothing as a name, so there is
 * no name here to draw — the bench does not invent one.
 */
export interface MockTicket {
  /** The number a person says out loud; `null` until the record allocates one. */
  readonly key: string | null;
  readonly title: string;
  readonly lane: BoardLane;
  readonly priority: Priority;
  /** When it was raised, as the project's event read answers. */
  readonly raisedAt: string;
  /** The workflow stage it stands at, as a word; `null` when none has started. */
  readonly stage: string | null;
  /** The blocker the record opened on it, in the words a person wrote. */
  readonly blocked: string | null;
  /** Whether a finding is waiting on a person. */
  readonly waiting: boolean;
}

/** The instant the bench calls "now", so every relative age is reproducible. */
export const NOW = "2026-08-24T19:40:00Z";

export const TICKETS: readonly MockTicket[] = [
  {
    key: "CTW-31",
    title: "The Tickets page, laid down first",
    lane: "in_progress",
    priority: "P1",
    raisedAt: "2026-08-24T19:12:00Z",
    stage: "Design",
    blocked: null,
    waiting: true,
  },
  {
    key: "CTW-30",
    title: "The rail is two workspaces, and a project is a scope",
    lane: "complete",
    priority: "P1",
    raisedAt: "2026-08-24T14:52:00Z",
    stage: "Closed",
    blocked: null,
    waiting: false,
  },
  {
    key: "CTW-29",
    title: "The harness is a card and an agent is a person",
    lane: "in_review",
    priority: "P1",
    raisedAt: "2026-08-24T11:08:00Z",
    stage: "Review",
    blocked: null,
    waiting: false,
  },
  {
    key: "CTW-28",
    title: "The walk asserts a job, not a page",
    lane: "in_review",
    priority: "P2",
    raisedAt: "2026-08-24T09:41:00Z",
    stage: "Review",
    blocked: null,
    waiting: false,
  },
  {
    key: "CTW-27",
    title: "A project key with a dot is refused at the door",
    lane: "blocked",
    priority: "P0",
    raisedAt: "2026-08-23T16:20:00Z",
    stage: "Implement",
    blocked: "Waiting on the operator to say whether the dotted key is kept.",
    waiting: false,
  },
  {
    key: "CTW-26",
    title: "The company page says what the operator said",
    lane: "ready",
    priority: "P1",
    raisedAt: "2026-08-23T10:05:00Z",
    stage: null,
    blocked: null,
    waiting: false,
  },
  {
    key: "CTW-25",
    title: "The cockpit's panes say so when the window cannot hold them",
    lane: "backlog",
    priority: "P2",
    raisedAt: "2026-08-22T20:33:00Z",
    stage: null,
    blocked: null,
    waiting: false,
  },
  {
    key: null,
    title: "Morning digest lands before the first stand-up",
    lane: "backlog",
    priority: "P2",
    raisedAt: "2026-08-22T07:15:00Z",
    stage: null,
    blocked: null,
    waiting: false,
  },
];

export interface MockProject {
  readonly key: string;
  readonly name: string;
  readonly prefix: string;
}

/** The projects this company records; the project picker offers exactly these. */
export const PROJECTS: readonly MockProject[] = [
  { key: "ctower", name: "ctower", prefix: "CTW" },
  { key: "mission-control", name: "Mission control", prefix: "MC" },
];

export const HERE: MockProject = PROJECTS[0] ?? { key: "ctower", name: "ctower", prefix: "CTW" };

export const COMPANY = "Manibo";

/**
 * The staff this company records, by the names their own components carry.
 *
 * They are real names from the company's record — and none of them can take a
 * ticket yet. A ticket goes to a principal the record names by identifier, and
 * no read this console can make turns one of these names into that identifier,
 * so the picker offers them dimmed with the reason rather than dropping them.
 */
export const STAFF: readonly string[] = ["Ada", "Luna", "Ox", "Sol", "Vela"];

/** How long ago, in the shortest true form. Never a locale, never a guess. */
export function ageOf(at: string, now: string = NOW): string {
  const minutes = Math.floor((Date.parse(now) - Date.parse(at)) / 60000);
  if (minutes < 60) {
    return `${String(Math.max(minutes, 1))}m`;
  }
  if (minutes < 1440) {
    return `${String(Math.floor(minutes / 60))}h`;
  }
  return `${String(Math.floor(minutes / 1440))}d`;
}

/**
 * The group a ticket falls in, in the reference's own words.
 *
 * The reference separates its list by how long ago, not by date, so a run of
 * rows reads as "this morning" rather than as a calendar. Three groups is the
 * whole vocabulary: anything older than a day is one group, because a list this
 * short gains nothing from a fourth.
 */
export function groupOf(at: string, now: string = NOW): string {
  const hours = Math.floor((Date.parse(now) - Date.parse(at)) / 3600000);
  if (hours < 12) {
    return "TODAY";
  }
  return hours < 36 ? "YESTERDAY" : "OLDER THAN A DAY";
}
