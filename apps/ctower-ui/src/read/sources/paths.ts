/**
 * Where the interim sources live, and the one rule about them.
 *
 * Wave 2 wires the remaining screens against control-plane sources that already
 * exist: Mission Control's append-only state files, the crontab, the systemd
 * user timers, this repository's git tree and worktrees, and the tmux capture
 * bridge. They are **interim**: each screen swaps to its native or #186 source
 * when that lands, and nothing outside `src/read/sources/` knows any of these
 * paths exist.
 *
 * Every one is read-only. This app opens these files for reading and runs
 * inspection commands; it never writes, locks, truncates, renames or appends to
 * another repository's live state.
 *
 * Every path is overridable, so an operator can point a screen at a copy, and
 * so the evidence drivers can exercise a source without touching live state.
 */

function environment(name: string, fallback: string): string {
  const value = process.env[name];
  return value === undefined || value === "" ? fallback : value;
}

export function missionControlRoot(): string {
  return environment("CTOWER_UI_MC_ROOT", "/srv/projects/mission-control");
}

export function inboxPath(): string {
  return environment("CTOWER_UI_INBOX_PATH", `${missionControlRoot()}/state/inbox.jsonl`);
}

export function heartbeatPath(): string {
  return environment("CTOWER_UI_HEARTBEAT_PATH", `${missionControlRoot()}/state/heartbeat.json`);
}

export function watchdogLogPath(): string {
  return environment(
    "CTOWER_UI_WATCHDOG_LOG_PATH",
    `${missionControlRoot()}/state/logs/ctower-beat-watchdog.log`
  );
}

export function crewLogPath(): string {
  return environment("CTOWER_UI_CREW_LOG_PATH", `${missionControlRoot()}/state/crew-log.jsonl`);
}

/** The directory whose files declare the seats the fleet can dispatch. */
export function personasRoot(): string {
  return environment("CTOWER_UI_PERSONAS_ROOT", `${missionControlRoot()}/personas`);
}

/**
 * Where seats write their task and status files, and the ledger that charges an
 * escape to a seat.
 *
 * Neither takes an override of its own. Both are fixed positions inside Mission
 * Control's tree, so `CTOWER_UI_MC_ROOT` already moves them together — and a
 * profile that could be pointed at a ledger from one fleet and a coordination
 * directory from another would be reading two different companies onto one page.
 */
export function coordinationRoot(): string {
  return `${missionControlRoot()}/coordination`;
}

export function escapesPath(): string {
  return `${missionControlRoot()}/state/escapes.jsonl`;
}

export function muxBridgePath(): string {
  return environment("CTOWER_UI_MUX_PATH", `${missionControlRoot()}/bin/mux`);
}

/** The repository the Files screen browses. Defaults to this app's own repo. */
export function filesRoot(): string {
  return environment("CTOWER_UI_FILES_ROOT", repositoryRoot());
}

/**
 * The repository git commands run in. `.` is deliberate: git resolves the
 * enclosing repository from any subdirectory, so the default needs no absolute
 * path baked into the bundle and the serve script can still pin it explicitly.
 */
export function repositoryRoot(): string {
  return environment("CTOWER_UI_REPO_ROOT", ".");
}

/** Which cadence source Heartbeats reads: the swap seam proven by the drivers. */
export function cadenceSourceName(): "cron" | "systemd" {
  return environment("CTOWER_UI_CADENCE_SOURCE", "cron") === "systemd" ? "systemd" : "cron";
}
