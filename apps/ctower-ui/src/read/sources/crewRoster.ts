import { readdir, readFile } from "node:fs/promises";
import { boundedProcess } from "../bounded";
import { stampText } from "../elapsed";
import { NO_WORK_SESSIONS as COST_SOURCE } from "../futureSources";
import { readAccountability } from "./escapesLedger";
import { scanJsonl } from "./jsonl";
import { readLandedChanges } from "./landedChanges";
import { attempted, noneOf, unreadOf, valueOf } from "./maybe";
import type { Known } from "./maybe";
import { crewNameOf, parseName } from "./crewNaming";
import { crewLogPath, personasRoot } from "./paths";
import { filtersOf, groupsOf, modelsOf, projectKeyOf, seatRowsOf } from "../rosterShape";
import { redacted } from "./redact";
import { changeReferencesIn, readCrewRecords } from "./signatures";
import type { ChangeReference } from "./signatures";
import { asRecord, asString, asStringOrNull } from "../json";
import type {
  CrewActivity,
  CrewLifecycleEntry,
  CrewLink,
  CrewLookup,
  CrewRoster,
  CrewRow,
  CrewUnknown,
} from "../interface";

/**
 * Interim source: the live tmux sessions joined to Mission Control's
 * append-only `state/crew-log.jsonl`, with the seat list read from the
 * personas directory.
 *
 * Three sources, three different failure modes, kept apart on purpose:
 *
 * * **tmux** says which crews are *alive*, and carries the `@project` tag the
 *   fleet sets when it spawns one. If it does not answer there is no roster at
 *   all, so that failure fails the whole reading — an empty roster would read as
 *   "nobody is working", which is the opposite claim.
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

const TASK_CAP = 220;

interface LogRecord {
  readonly crew: string;
  readonly at: string;
  readonly model: string | null;
  readonly task: string | null;
  readonly status: string | null;
  readonly project: string | null;
  /** Free text the writing seat added to the entry, when it added any. */
  readonly comment: string | null;
}

interface LiveSession {
  readonly name: string;
  readonly createdAt: number | null;
  /** The session's own `@project` tag, when the fleet set one. */
  readonly project: string | null;
  /**
   * When this session last produced output, as tmux records it. The roster
   * does not show it; a profile does, because "still running" and "last said
   * something four hours ago" are different answers to "is this crew alive".
   */
  readonly activityAt: number | null;
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
      comment: asStringOrNull(row.comment, "crew-log.comment"),
    };
  } catch {
    return null;
  }
}

/**
 * The `@project` tag per session, keyed by session name.
 *
 * This is a second `list-sessions` rather than a wider format on the first: the
 * liveness listing is the reading that must not fail, and a tag lookup that
 * cannot answer must not be able to empty the roster. A tmux without the option
 * prints an empty field, which is a session with no tag — not a failed read.
 */
async function sessionProjects(): Promise<ReadonlyMap<string, string>> {
  const tagged = new Map<string, string>();
  const listing = await attempted(
    async () => await boundedProcess({ op: "tmux.crewProjects" }),
    (text) => text.trim().length === 0,
    "tmux reported no session tag"
  );
  if (listing.known !== "value") {
    return tagged;
  }
  for (const line of listing.value.split("\n")) {
    const [name = "", project = ""] = line.split("\t");
    if (name.trim().length > 0 && project.trim().length > 0) {
      tagged.set(name.trim(), project.trim());
    }
  }
  return tagged;
}

async function liveSessions(): Promise<readonly LiveSession[]> {
  const listing = await boundedProcess({ op: "tmux.crews" });
  const tagged = await sessionProjects();
  return listing
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line): LiveSession => {
      const [name = "", created = "", active = ""] = line.split("\t");
      const epoch = Number.parseInt(created, 10);
      const last = Number.parseInt(active, 10);
      return {
        name,
        createdAt: Number.isFinite(epoch) ? epoch : null,
        project: tagged.get(name) ?? null,
        activityAt: Number.isFinite(last) ? last : null,
      };
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

function harnessOf(model: Known<string>): Known<string> {
  // the harness is derived from the model, so a missing model is stated as the
  // reason there is no harness rather than repeated verbatim beside itself
  if (model.known === "none") {
    return noneOf(`${model.why}, so no harness can be derived`);
  }
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

/**
 * Which project a crew is on, from the two sources that record one.
 *
 * The crew log is preferred: it is the crew's own declaration, written as it
 * works. The session tag is the fallback, and it is a *recorded* fact too — the
 * fleet sets `@project` when it spawns the session. Round-3 QA (#237) found the
 * roster reading only the log and filing four of seventeen live crews under
 * "project not recorded" while tmux, which this source already shells out to for
 * liveness, held the project for three of them.
 *
 * Nothing is inferred from the crew's *name*. A session with neither a logged
 * project nor a tag stays "not recorded", because guessing a project from the
 * spelling of an identifier is the inference SPEC INV-66 forbids by name — and a
 * phantom bucket of one honest row is better than three rows filed under a
 * project nobody recorded.
 */
export function projectOf(
  logged: string | null,
  tagged: string | null,
  log: LogOutcome
): Known<string> {
  const fromLog = knownText(logged, "not recorded", log);
  if (fromLog.known === "value") {
    return fromLog;
  }
  if (tagged !== null && tagged.trim().length > 0) {
    return valueOf(redacted(tagged.trim()));
  }
  // an unread log stays unread: the tag did not answer either, so this surface
  // does not know whether a project is recorded for this crew
  return fromLog;
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
      sessionName: redacted(session.name),
      project: projectOf(record?.project ?? null, session.project, log),
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
      "live tmux sessions (liveness and the session's @project tag) joined to the crew log (model, task, status, project); the project is the log's when it recorded one and the session tag otherwise; the seat comes from the crew name and is never guessed from it",
    tail: {
      totalLines: scan.totalLines,
      malformed: scan.malformed,
      partialTail: scan.partialTail,
      sourcePath: path,
    },
  };
}

/* ── one crew in full ──────────────────────────────────────────────────────
   The same three sources the roster joins, read for a single name, plus the
   records that seat wrote about itself. The roster answers "who is working";
   this answers "what has this one crew done, and who stands behind it". */

/** Lifecycle entries shown, newest last. A cap is stated, never silent. */
const LIFECYCLE_CAP = 40;

/** The pane a session is showing: its working directory and its process. */
async function paneOf(session: string): Promise<{ cwd: Known<string>; running: Known<string> }> {
  const panes = await attempted(
    async () => await boundedProcess({ op: "tmux.panes" }),
    (text) => text.trim().length === 0,
    "tmux reported no pane for any session"
  );
  if (panes.known !== "value") {
    // a pane listing that failed is not a session without a directory
    return { cwd: panes, running: panes };
  }
  for (const line of panes.value.split("\n")) {
    const [name, cwd, command] = line.split("\t");
    if (name === session && cwd !== undefined && command !== undefined) {
      return { cwd: valueOf(redacted(cwd)), running: valueOf(redacted(command)) };
    }
  }
  const why = "tmux lists no pane for this session";
  return { cwd: noneOf(why), running: noneOf(why) };
}

/** One git fact about the directory a crew works in, or why there is none. */
async function gitFact(
  cwd: Known<string>,
  inspect: (root: string) => Promise<string>,
  empty: string
): Promise<Known<string>> {
  if (cwd.known !== "value") {
    return cwd;
  }
  const root = cwd.value;
  return await attempted(
    async () => redacted((await inspect(root)).trim()),
    (text) => text.length === 0,
    empty
  );
}

function lifecycleOf(
  records: readonly LogRecord[],
  log: LogOutcome,
  nowMs: number
): readonly CrewLifecycleEntry[] {
  const from = Math.max(0, records.length - LIFECYCLE_CAP);
  const shown = records.slice(from);
  return shown.map((record, index): CrewLifecycleEntry => {
    const status = knownText(record.status, "no status recorded", log);
    // compared against the real predecessor, not the first entry shown: a cap
    // must not turn the oldest visible row into a task change that never was
    const previous = records[from + index - 1];
    return {
      at: redacted(record.at),
      ago: loggedAgo(record.at, nowMs),
      status,
      activity: activityOf(status),
      task: knownText(record.task, "no task recorded", log),
      model: knownText(record.model, "no model recorded", log),
      comment: knownText(record.comment, "no comment recorded", log),
      // the log has no engagement field; a task line that changes is the only
      // mark the record carries for "this crew was pointed at something else"
      opensEngagement: previous?.task !== record.task,
    };
  });
}

function linksOf(session: string, row: CrewRow): readonly CrewLink[] {
  const links: CrewLink[] = [
    { label: "Org", href: "/team", what: "every crew alive on the fleet" },
  ];
  if (row.seatLabel.known === "value") {
    links.push({
      label: `${row.seatLabel.value} crews`,
      href: `/team?seat=${encodeURIComponent(row.seatLabel.value)}`,
      what: "the roster filtered to this seat",
    });
  }
  // both of these are keyed on the session name, which exists because this
  // profile only renders for a session tmux is listing right now
  links.push(
    {
      label: "Workspace",
      href: `/workspace?seat=${encodeURIComponent(session)}`,
      what: "what this session was handed at start",
    },
    {
      label: "Feed",
      href: `/feed?seat=${encodeURIComponent(session)}`,
      what: "this session's pane, read-only",
    }
  );
  return links;
}

function missingOf(
  crew: string,
  records: readonly LogRecord[],
  log: LogOutcome,
  live: number,
  nowMs: number
): CrewUnknown {
  const last = records.at(-1);
  const ago = last === undefined ? null : loggedAgo(last.at, nowMs);
  return {
    crew: redacted(crew),
    logged:
      last === undefined
        ? knownText(null, "the crew log has never recorded this name", log)
        : knownText(
            `${last.status ?? "no status"} · ${last.at}${ago?.known === "value" ? ` · ${ago.value}` : ""}${
              last.task === null ? "" : ` — ${last.task.slice(0, TASK_CAP)}`
            }`,
            "the crew log has never recorded this name",
            log
          ),
    liveCrews: live,
    checked: [
      `the ${String(live)} sessions tmux is listing right now`,
      crewLogPath(),
      personasRoot(),
    ],
  };
}

/**
 * Read one crew in full.
 *
 * Not finding the crew is an answer, not a failure: tmux was reached and does
 * not list it. So the lookup stays `present` and carries what *was* found —
 * whether the crew log has ever recorded the name, and how many crews are alive
 * — while tmux failing to answer at all still throws, and arrives at the screen
 * as an unreachable read.
 */
export async function readCrewProfile(crew: string): Promise<CrewLookup> {
  const nowMs = Date.now();
  const sessions = await liveSessions();
  const seats = await declaredSeats();

  const path = crewLogPath();
  const log = await readCrewLog(path);
  const scan = scanJsonl(log.read ? log.text : "", logShape);
  const mine = scan.records.filter((record) => record.crew === crew);
  const tail = {
    totalLines: scan.totalLines,
    malformed: scan.malformed,
    partialTail: scan.partialTail,
    sourcePath: path,
  };

  const session = sessions.find((entry) => crewNameOf(entry.name) === crew);
  if (session === undefined) {
    return {
      found: "no-such-crew",
      missing: missingOf(crew, mine, log, sessions.length, nowMs),
    };
  }

  const latest = new Map<string, LogRecord>();
  const newest = mine.at(-1);
  if (newest !== undefined) {
    latest.set(crew, newest);
  }
  const row = rowsOf([session], latest, log, seats, nowMs)[0];
  if (row === undefined) {
    throw new Error("the roster produced no row for a session tmux is listing");
  }

  const pane = await paneOf(session.name);
  const [branch, head, headSubject] = await Promise.all([
    gitFact(
      pane.cwd,
      async (root) => await boundedProcess({ op: "git.branch", root }),
      "this directory is not a git checkout"
    ),
    gitFact(
      pane.cwd,
      async (root) => await boundedProcess({ op: "git.revision", root }),
      "this directory is not a git checkout"
    ),
    gitFact(
      pane.cwd,
      async (root) => await boundedProcess({ op: "git.headSubject", root }),
      "no commit subject is recorded"
    ),
  ]);

  const records = await readCrewRecords(crew, row.project);
  // each log entry carries its own project, so a reference this crew wrote
  // while it was on another fleet's repository is checked against that trunk;
  // an entry that left the field empty falls back to the crew's project, which
  // the row then names as the derivation it is
  const logged: readonly ChangeReference[] = mine.flatMap((record) => {
    if (record.task === null) {
      return [];
    }
    const own = knownText(record.project, "not recorded", log);
    return changeReferencesIn(record.task, {
      citedIn: "the crew log",
      project: own.known === "value" ? own : row.project,
      projectFromCrew: own.known !== "value",
    });
  });
  const [landed, accountability] = await Promise.all([
    readLandedChanges([...records.references, ...logged], nowMs),
    readAccountability(row.seat.known === "value" ? row.seat.value : null, nowMs),
  ]);

  return {
    found: "crew",
    profile: {
      row,
      sessionName: redacted(session.name),
      spawnedAt:
        session.createdAt === null
          ? unreadOf("tmux reported no start time for this session")
          : valueOf(stampText(new Date(session.createdAt * 1_000).toISOString())),
      lastOutput:
        session.activityAt === null
          ? unreadOf("tmux reported no last-activity time for this session")
          : valueOf(`${elapsed(session.activityAt * 1_000, nowMs)} since tmux last saw output`),
      worktree: pane.cwd,
      branch,
      head,
      headSubject,
      running: pane.running,
      links: linksOf(session.name, row),
      lifecycle: lifecycleOf(mine, log, nowMs),
      lifecycleNote:
        mine.length > LIFECYCLE_CAP
          ? `the newest ${String(LIFECYCLE_CAP)} of ${String(mine.length)} entries the crew log holds for this crew`
          : `every one of the ${String(mine.length)} ${mine.length === 1 ? "entry" : "entries"} the crew log holds for this crew`,
      delivered: landed.changes,
      deliveredNote: landed.note,
      claims: records.claims,
      signatures: records.signatures,
      claimsNote:
        records.outcome.known === "value"
          ? `${records.outcome.value}${records.beyondCap === 0 ? "" : `; ${String(records.beyondCap)} older ${records.beyondCap === 1 ? "file was" : "files were"} not opened`}`
          : records.outcome.known === "none"
            ? records.outcome.why
            : records.outcome.reason,
      accountability,
      cost: COST_SOURCE,
      observedAt: new Date(nowMs).toISOString(),
      sourceNote:
        "identity and liveness from the live tmux session; model, task, status and project from the crew log; the seat from the crew name against the personas directory",
      tail,
    },
  };
}
