import { readdir, readFile } from "node:fs/promises";
import { boundedProcess } from "../bounded";
import { scanJsonl } from "./jsonl";
import { noneOf, unreadOf, valueOf } from "./maybe";
import type { Known } from "./maybe";
import { crewLogPath, personasRoot } from "./paths";
import { redacted } from "./redact";
import { asRecord, asString, asStringOrNull } from "../json";
import type {
  CrewActivity,
  CrewRoster,
  CrewRow,
  ModelShare,
  ProjectRoster,
  RosterFilter,
  SeatRow,
} from "../interface";

/**
 * Interim source: the live tmux sessions joined to Mission Control's
 * append-only `state/crew-log.jsonl`, with the seat list read from the
 * personas directory.
 *
 * Three sources, three different failure modes, kept apart on purpose:
 *
 * * **tmux** says which crews are *alive*. If it does not answer there is no
 *   roster at all, so that failure fails the whole reading — an empty roster
 *   would read as "nobody is working", which is the opposite claim.
 * * **the crew log** says what each crew is *doing*. It is appended to by every
 *   seat on the fleet while this page renders, so it is scanned tolerantly and
 *   its mid-write tail is counted. A crew the log has never mentioned is
 *   `none` — the log answered and holds nothing for it. A log that could not be
 *   read at all makes every one of those fields `unread`, never `none`.
 * * **the personas directory** declares the seats. A crew whose name matches no
 *   declared seat is counted as unseated and still shown; it is not dropped and
 *   not filed under a seat this surface made up.
 *
 * Read-only throughout. Every string a screen sees passes `redacted` first: a
 * crew's task line is coordination text authored by another seat.
 */

/** How a crew name's persona token maps to a declared seat file. */
const SEAT_ALIASES: Readonly<Record<string, string>> = {
  em: "engineering-manager",
  writer: "tech-writer",
  release: "release-manager",
};

/**
 * How a declared seat is spelled and abbreviated on screen. This is display
 * only: the seat list itself is whatever the personas directory holds, and a
 * seat missing from this table still gets a row — spelled from its file name.
 */
const SEAT_DISPLAY: Readonly<Record<string, readonly [string, string]>> = {
  ceo: ["CEO", "CE"],
  commander: ["Commander", "CM"],
  cso: ["CSO", "CS"],
  designer: ["Designer", "DS"],
  devops: ["DevOps", "DO"],
  engineer: ["Engineer", "EN"],
  "engineering-manager": ["Eng manager", "EM"],
  qa: ["QA", "QA"],
  "release-manager": ["Release", "RL"],
  review: ["Review", "RV"],
  "tech-writer": ["Writer", "WR"],
};

/**
 * The status words the crew log actually writes, sorted into the product's
 * three marks. This is a classification of someone else's vocabulary, so it is
 * declared here and stated on the page rather than hidden in a component.
 */
const IN_FLIGHT = new Set([
  "working",
  "in-progress",
  "relaunched",
  "spawned",
  "switched",
  "review",
]);
const HELD = new Set([
  "blocked",
  "changes-requested",
  "failed",
  "aborted",
  "interrupted",
  "spawn_failed",
]);
const ACTIVITY_RULE =
  "the crew log's own status word: working · in-progress · relaunched · spawned · switched · review count as in flight; blocked · changes-requested · failed · aborted · interrupted · spawn_failed as held; every other recorded word as parked";

/** Which harness runs a model family. A derivation, labelled as one on screen. */
const HARNESSES: readonly (readonly [RegExp, string])[] = [
  [/^(?:opus|sonnet|haiku|fable|claude)/u, "Claude Code"],
  [/^(?:gpt|o[0-9]|codex|sol)/u, "Codex"],
  [/^glm/u, "z.ai"],
];

const MC_PREFIX = "mc-";
const TASK_CAP = 220;

interface LogRecord {
  readonly crew: string;
  readonly at: string;
  readonly model: string | null;
  readonly task: string | null;
  readonly status: string | null;
  readonly project: string | null;
}

interface LiveSession {
  readonly name: string;
  readonly createdAt: number | null;
}

function logShape(value: unknown): LogRecord | null {
  try {
    const row = asRecord(value, "crew-log.line");
    return {
      crew: asString(row.crew, "crew-log.crew"),
      at: asStringOrNull(row.date, "crew-log.date") ?? "",
      model: asStringOrNull(row.model, "crew-log.model"),
      task: asStringOrNull(row.task, "crew-log.task"),
      status: asStringOrNull(row.status, "crew-log.status"),
      project: asStringOrNull(row.project, "crew-log.project"),
    };
  } catch {
    return null;
  }
}

/** The crew as the fleet names it, with the mux prefix the socket adds. */
function crewNameOf(session: string): string {
  return session.startsWith(MC_PREFIX) ? session.slice(MC_PREFIX.length) : session;
}

async function liveSessions(): Promise<readonly LiveSession[]> {
  const listing = await boundedProcess({ op: "tmux.crews" });
  return listing
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line): LiveSession => {
      const [name = "", created = ""] = line.split("\t");
      const epoch = Number.parseInt(created, 10);
      return { name, createdAt: Number.isFinite(epoch) ? epoch : null };
    })
    .filter((session) => session.name.length > 0);
}

/** The seats the fleet declares, read from the personas directory. */
async function declaredSeats(): Promise<Known<readonly string[]>> {
  try {
    const entries = await readdir(personasRoot());
    const seats = entries
      .filter((entry) => entry.endsWith(".md"))
      .map((entry) => entry.slice(0, -".md".length))
      .filter((entry) => entry === entry.toLowerCase() && !entry.includes("superseded"))
      .filter((entry) => entry !== "README" && entry !== "AGENTS")
      .sort((left, right) => left.localeCompare(right));
    return seats.length === 0 ? noneOf("the personas directory declares no seat") : valueOf(seats);
  } catch (error: unknown) {
    return unreadOf(
      error instanceof Error ? error.message : "the personas directory could not be listed"
    );
  }
}

function seatLabelOf(seat: string): string {
  const declared = SEAT_DISPLAY[seat];
  if (declared !== undefined) {
    return declared[0];
  }
  return seat
    .split("-")
    .map((word, index) =>
      index === 0 ? `${word.slice(0, 1).toUpperCase()}${word.slice(1)}` : word
    )
    .join(" ");
}

function initialsOf(seat: string): string {
  const declared = SEAT_DISPLAY[seat];
  if (declared !== undefined) {
    return declared[1];
  }
  const parts = seat.split("-");
  const first = parts[0] ?? "";
  const second = parts[1];
  return (second === undefined ? first.slice(0, 2) : `${first.slice(0, 1)}${second.slice(0, 1)}`)
    .toUpperCase()
    .padEnd(2, "·");
}

function harnessOf(model: Known<string>): Known<string> {
  if (model.known !== "value") {
    return model;
  }
  const normalised = model.value.toLowerCase();
  const matched = HARNESSES.find(([pattern]) => pattern.test(normalised));
  return matched === undefined ? noneOf("harness not recorded") : valueOf(matched[1]);
}

function activityOf(status: Known<string>): CrewActivity {
  if (status.known !== "value") {
    return "unrecorded";
  }
  const word = status.value.toLowerCase();
  if (IN_FLIGHT.has(word)) {
    return "in-flight";
  }
  return HELD.has(word) ? "held" : "parked";
}

function elapsed(fromMs: number, nowMs: number): string {
  const minutes = Math.max(0, Math.floor((nowMs - fromMs) / 60_000));
  const hours = Math.floor(minutes / 60);
  return hours === 0 ? `${String(minutes)}m` : `${String(hours)}h ${String(minutes % 60)}m`;
}

/**
 * The crew log writes a naive local stamp. This host writes and reads it, so it
 * is parsed in the same zone; a stamp that does not parse stays unread rather
 * than becoming a plausible age.
 */
function loggedAgo(at: string, nowMs: number): Known<string> {
  if (at.length === 0) {
    return noneOf("no time recorded");
  }
  const parsed = Date.parse(at.replace(" ", "T"));
  return Number.isNaN(parsed)
    ? unreadOf(`the recorded stamp ${at} could not be read as a time`)
    : valueOf(`logged ${elapsed(parsed, nowMs)} ago`);
}

/** Split `<persona>-<request>-<slug>`; a part the name omits says so. */
function parseName(
  crew: string,
  seats: Known<readonly string[]>
): Pick<CrewRow, "seat" | "seatLabel" | "seatInitials" | "request" | "slug" | "flag"> {
  const parts = crew.split("-");
  const token = parts[0] ?? "";
  const declared = seats.known === "value" ? seats.value : [];
  const candidate = SEAT_ALIASES[token] ?? token;
  const seatKey = declared.find((entry) => entry === candidate);
  const seat: Known<string> =
    seats.known === "unread"
      ? unreadOf(seats.reason)
      : seatKey === undefined
        ? noneOf(`no seat named ${token}`)
        : valueOf(seatKey);
  const request = parts[1];
  const carriesRequest = request !== undefined && /^(?:r?[0-9]+|i[0-9]+|gh[0-9]+)$/iu.test(request);
  const slugParts = carriesRequest ? parts.slice(2) : parts.slice(1);
  return {
    seat,
    seatLabel: seat.known === "value" ? valueOf(seatLabelOf(seat.value)) : seat,
    seatInitials: seat.known === "value" ? valueOf(initialsOf(seat.value)) : seat,
    request: carriesRequest ? valueOf(redacted(request)) : noneOf("no request id"),
    slug: slugParts.length === 0 ? noneOf("no slug") : valueOf(redacted(slugParts.join("-"))),
    // the naming rule is Mission Control's, and a row that breaks it is flagged
    // rather than normalised into looking compliant
    flag: carriesRequest
      ? null
      : "this crew name carries no request id, so the name alone does not say which request it serves",
  };
}

/**
 * How the crew log answered. A file that is not there and a file that could not
 * be read are different answers: the first means nothing has been logged, the
 * second means this surface does not know what has been.
 */
type LogOutcome =
  | { readonly read: true; readonly text: string }
  | { readonly read: false; readonly missing: boolean; readonly reason: string };

async function readCrewLog(path: string): Promise<LogOutcome> {
  try {
    return { read: true, text: await readFile(path, "utf8") };
  } catch (error: unknown) {
    const code = (error as NodeJS.ErrnoException | null)?.code;
    return code === "ENOENT"
      ? { read: false, missing: true, reason: `no crew log exists at ${path}` }
      : {
          read: false,
          missing: false,
          reason: error instanceof Error ? error.message : "the crew log could not be read",
        };
  }
}

function knownText(value: string | null, why: string, log: LogOutcome): Known<string> {
  if (!log.read) {
    return log.missing ? noneOf(log.reason) : unreadOf(log.reason);
  }
  return value === null || value.trim().length === 0 ? noneOf(why) : valueOf(redacted(value));
}

function rowsOf(
  sessions: readonly LiveSession[],
  latest: ReadonlyMap<string, LogRecord>,
  log: LogOutcome,
  seats: Known<readonly string[]>,
  nowMs: number
): readonly CrewRow[] {
  return sessions.map((session): CrewRow => {
    const crew = crewNameOf(session.name);
    const record = latest.get(crew);
    const parsed = parseName(crew, seats);
    const status = knownText(record?.status ?? null, "no status recorded", log);
    const model = knownText(record?.model ?? null, "no model recorded", log);
    const task = knownText(
      record?.task === undefined || record.task === null
        ? null
        : record.task.slice(0, TASK_CAP) + (record.task.length > TASK_CAP ? "…" : ""),
      "no task recorded",
      log
    );
    return {
      ...parsed,
      name: redacted(crew),
      project: knownText(record?.project ?? null, "not recorded", log),
      model,
      harness: harnessOf(model),
      task,
      status,
      activity: activityOf(status),
      upFor:
        session.createdAt === null
          ? unreadOf("tmux reported no start time for this session")
          : valueOf(`up ${elapsed(session.createdAt * 1_000, nowMs)}`),
      loggedAgo: !log.read
        ? knownText(null, log.reason, log)
        : record === undefined
          ? noneOf("never logged")
          : loggedAgo(record.at, nowMs),
    };
  });
}

const NOT_RECORDED = "project not recorded";

function projectKeyOf(row: CrewRow): string {
  return row.project.known === "value" ? row.project.value : NOT_RECORDED;
}

function groupsOf(rows: readonly CrewRow[]): readonly ProjectRoster[] {
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

function seatRowsOf(
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

function modelsOf(rows: readonly CrewRow[]): readonly ModelShare[] {
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

function filtersOf(rows: readonly CrewRow[], of: (row: CrewRow) => string | null): RosterFilter[] {
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

export async function readCrewRoster(
  project: string | null,
  seat: string | null
): Promise<CrewRoster> {
  const nowMs = Date.now();
  // tmux is the liveness source: no answer means no roster, not an empty one
  const sessions = await liveSessions();
  const seats = await declaredSeats();

  const path = crewLogPath();
  const log = await readCrewLog(path);
  const scan = scanJsonl(log.read ? log.text : "", logShape);
  const latest = new Map<string, LogRecord>();
  for (const record of scan.records) {
    latest.set(record.crew, record);
  }

  const all = rowsOf(sessions, latest, log, seats, nowMs);
  const seatKeyOf = (row: CrewRow): string | null =>
    row.seatLabel.known === "value" ? row.seatLabel.value : null;
  const selectedProject =
    project !== null && all.some((row) => projectKeyOf(row) === project) ? project : null;
  const selectedSeat = seat !== null && all.some((row) => seatKeyOf(row) === seat) ? seat : null;

  // A chip counts what clicking it would reveal, which means counting against
  // the *other* filter's current selection. A chip that printed the fleet-wide
  // number while a project was selected would promise rows it cannot show.
  const underSeat = all.filter((row) => selectedSeat === null || seatKeyOf(row) === selectedSeat);
  const underProject = all.filter(
    (row) => selectedProject === null || projectKeyOf(row) === selectedProject
  );
  const projectFilters = filtersOf(underSeat, projectKeyOf);
  const seatFilters = filtersOf(underProject, seatKeyOf);
  const rows = underSeat.filter(
    (row) => selectedProject === null || projectKeyOf(row) === selectedProject
  );

  const groups = groupsOf(rows);
  const columns = groups.map((group) => group.key);
  return {
    columns,
    seats: seatRowsOf(rows, seats, columns),
    columnTotals: columns.map(
      (column) => rows.filter((row) => projectKeyOf(row) === column).length
    ),
    total: rows.length,
    groups,
    projectFilters,
    seatFilters,
    // what "all projects" and "all seats" would reveal, under the other filter
    allProjectsCount: underSeat.length,
    allSeatsCount: underProject.length,
    selectedProject,
    selectedSeat,
    inFlight: rows.filter((row) => row.activity === "in-flight").length,
    parked: rows.filter((row) => row.activity === "parked").length,
    held: rows.filter((row) => row.activity === "held").length,
    unrecorded: rows.filter((row) => row.activity === "unrecorded").length,
    models: modelsOf(rows),
    unseated: rows.filter((row) => row.seat.known !== "value").length,
    observedAt: new Date(nowMs).toISOString(),
    seatSource:
      seats.known === "value"
        ? `${String(seats.value.length)} seats declared in ${personasRoot()}`
        : "the seat list was not read, so the grid below has no rows to put crews in",
    activityRule: ACTIVITY_RULE,
    sourceNote:
      "live tmux sessions (liveness) joined to the crew log (model, task, status, project); the seat comes from the crew name",
    tail: {
      totalLines: scan.totalLines,
      malformed: scan.malformed,
      partialTail: scan.partialTail,
      sourcePath: path,
    },
  };
}
