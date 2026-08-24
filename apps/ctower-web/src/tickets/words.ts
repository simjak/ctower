import type { BoardLane, Priority } from "@ctower/client";

/**
 * The words the four ticket screens say, and the record's words they replace.
 *
 * The operator's ruling of 2026-08-24 ("I need nice non technical UI") froze a
 * table: a lane is a phrase a person uses, a stage is the job it names, a
 * priority is a word only when the record treats it differently, and an instant
 * is a clock rather than a stamp. Every mapping below is one row of that table.
 *
 * Nothing here invents a state. A lane and a stage are closed sets the record
 * owns; a key this file does not know is said as itself with its punctuation
 * softened, because a workflow a company authors tomorrow is a real stage and
 * printing nothing for it would be worse than printing its own name.
 *
 * Times are the record's own, in UTC. The rule that two operators comparing
 * screens read the same number survives the directive — what the directive
 * removed is the machine spelling, so `14:02Z` becomes `2:02pm` and not the
 * reader's own afternoon.
 */
const LANE: Readonly<Record<BoardLane, string>> = {
  backlog: "Waiting",
  ready: "Ready to start",
  in_progress: "Being worked on",
  in_review: "In review",
  blocked: "Stuck",
  complete: "Done",
};

/** The six lanes, in the order the board reads them. */
export const LANES: readonly BoardLane[] = [
  "backlog",
  "ready",
  "in_progress",
  "in_review",
  "blocked",
  "complete",
];

export function laneWord(lane: BoardLane): string {
  return LANE[lane];
}

/**
 * A lane's tone. Only two lanes earn colour: work that is stuck is the one
 * thing on this screen a person has to act on, and work that is finished is the
 * one thing they can stop reading. The other four are states, not signals.
 */
export function laneTone(lane: BoardLane): "neutral" | "amber" | "ok" {
  if (lane === "blocked") {
    return "amber";
  }
  return lane === "complete" ? "ok" : "neutral";
}

/**
 * The factory's stages, as the jobs they are.
 *
 * These keys are the workflow pack's own (`packs/workflows`), and a stage is
 * the one machine word an operator would otherwise meet on every ticket. A key
 * no pack here declares is title-cased rather than dropped.
 */
const STAGE: Readonly<Record<string, string>> = {
  intake: "Intake",
  think: "Think",
  plan: "Plan",
  design: "Design",
  implement: "Build",
  "local-verification-qa": "QA",
  "risk-derived-review": "Review",
  documentation: "Docs",
  "release-preflight": "Ship",
  merge: "Merge",
  "staging-deploy": "Staging",
  "staging-qa": "Recheck",
  "production-deploy": "Live",
  "production-smoke-live-qa": "Smoke",
  retro: "Retro",
  "resolve-close": "Closed",
};

export function stageWord(key: string): string {
  const known = STAGE[key];
  if (known !== undefined) {
    return known;
  }
  const said = key.replace(/[_-]+/g, " ").trim();
  return said === "" ? "Unnamed" : said.charAt(0).toUpperCase() + said.slice(1);
}

/**
 * Priority, and the one the record treats as authority rather than as an
 * opinion. Raising an urgent ticket is the operator's own power, so it is the
 * only priority that renders on a list at all.
 */
const PRIORITY: Readonly<Record<Priority, string>> = {
  P0: "Urgent",
  P1: "Normal",
  P2: "Low",
};

export function priorityWord(priority: Priority): string {
  return PRIORITY[priority];
}

/** The number a person says out loud, or the honest absence of one. */
export function numberWord(displayKey: string | null): string {
  return displayKey ?? "no number yet";
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** How long ago, in the shortest true phrase: `28 min`, `4 hours`, `3 days`. */
export function ageWords(at: string, now: number): string {
  const since = now - Date.parse(at);
  if (!Number.isFinite(since) || since < MINUTE) {
    return "just now";
  }
  if (since < HOUR) {
    return count(Math.floor(since / MINUTE), "min", "min");
  }
  if (since < DAY) {
    return count(Math.floor(since / HOUR), "hour", "hours");
  }
  return count(Math.floor(since / DAY), "day", "days");
}

function count(many: number, one: string, more: string): string {
  return `${String(many)} ${many === 1 ? one : more}`;
}

/** The band a raised-at falls in, which is how the list is grouped. */
export function bandWord(at: string, now: number): string {
  const since = now - Date.parse(at);
  if (!Number.isFinite(since)) {
    return "Earlier";
  }
  if (since < DAY) {
    return "Today";
  }
  return since < 2 * DAY ? "Yesterday" : "Earlier";
}

/** The clock a recorded instant reads at, in the record's own hours. */
export function clockWords(at: string): string {
  const when = new Date(at);
  if (Number.isNaN(when.getTime())) {
    return "an unrecorded time";
  }
  const hour = when.getUTCHours();
  const minute = String(when.getUTCMinutes()).padStart(2, "0");
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${String(twelve)}:${minute}${hour < 12 ? "am" : "pm"}`;
}

/** A moment said the way a person would: today by its clock, older by its age. */
export function whenWords(at: string, now: number): string {
  const since = now - Date.parse(at);
  if (!Number.isFinite(since)) {
    return "an unrecorded time";
  }
  return since < DAY ? `Today, ${clockWords(at)}` : `${ageWords(at, now)} ago`;
}

/** A span the record measured, in the largest unit that stays true. */
export function spanWords(seconds: number): string {
  if (seconds < 60) {
    return count(Math.round(seconds), "second", "seconds");
  }
  if (seconds < 3600) {
    return count(Math.round(seconds / 60), "minute", "minutes");
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return minutes === 0 ? count(hours, "hour", "hours") : `${String(hours)}h ${String(minutes)}m`;
}
