import { boundedProcess } from "../bounded";
import { missionControlRoot, muxBridgePath } from "./paths";
import { carriesRedaction, redacted } from "./redact";
import type { PaneCapture, SessionWorkspace } from "../interface";

/**
 * Interim source: the tmux capture bridge, read-only.
 *
 * `mux list` names the live crews and what each was handed — session, harness
 * and working directory. `mux read <crew>` captures that crew's pane. Both are
 * reads: this app never calls `spawn`, `send`, `submit` or `kill`, and the
 * bounded process reader only accepts the argv it is given.
 *
 * A pane is the most exposed text on this surface — it is whatever a seat has
 * on screen right now — so every captured line passes through `redacted`, and
 * the screen states when a line was changed by it.
 */

const PANE_LINES = 120;

export interface CrewRow {
  readonly crew: string;
  readonly session: string;
  readonly harness: string;
  readonly cwd: string;
}

function parseCrews(text: string): readonly CrewRow[] {
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .flatMap((line) => {
      const [crew, session, harness, cwd] = line.split("\t");
      return crew === undefined ||
        session === undefined ||
        harness === undefined ||
        cwd === undefined
        ? []
        : [{ crew, session, harness, cwd }];
    });
}

async function crews(): Promise<readonly CrewRow[]> {
  return parseCrews(
    await boundedProcess({
      command: muxBridgePath(),
      args: ["list"],
      cwd: missionControlRoot(),
    })
  );
}

function chosen(rows: readonly CrewRow[], requested: string | null): CrewRow | null {
  return rows.find((row) => row.crew === requested) ?? rows[0] ?? null;
}

export async function readSessionPane(requested: string | null): Promise<PaneCapture> {
  const rows = await crews();
  const row = chosen(rows, requested);
  if (row === null) {
    throw new Error("the capture bridge lists no live crew");
  }
  const raw = await boundedProcess({
    command: muxBridgePath(),
    args: ["read", row.crew, "-n", PANE_LINES.toString()],
    cwd: missionControlRoot(),
    maxBytes: 400_000,
  });
  const lines = raw.split("\n");
  return {
    crew: row.crew,
    session: row.session,
    harness: row.harness,
    cwd: row.cwd,
    lines: lines.map(redacted),
    capturedAt: new Date().toISOString(),
    wasRedacted: lines.some(carriesRedaction),
    crews: rows.map((entry) => entry.crew),
  };
}

export async function readSessionWorkspace(requested: string | null): Promise<SessionWorkspace> {
  const rows = await crews();
  const row = chosen(rows, requested);
  if (row === null) {
    throw new Error("the capture bridge lists no live crew");
  }
  const inWorktree = async (args: readonly string[]): Promise<string> => {
    try {
      return (await boundedProcess({ command: "git", args: ["-C", row.cwd, ...args] })).trim();
    } catch {
      // a crew whose cwd is not a git checkout is a real answer, not a failure
      return "";
    }
  };
  const branch = await inWorktree(["rev-parse", "--abbrev-ref", "HEAD"]);
  const head = await inWorktree(["rev-parse", "--short=8", "HEAD"]);
  const subject = await inWorktree(["log", "-1", "--format=%s"]);
  const project = await inWorktree(["rev-parse", "--show-toplevel"]);
  return {
    crew: row.crew,
    session: row.session,
    harness: row.harness,
    cwd: row.cwd,
    branch: branch.length === 0 ? null : branch,
    head: head.length === 0 ? null : head,
    headSubject: subject.length === 0 ? null : redacted(subject),
    project: project.length === 0 ? null : project,
    crews: rows.map((entry) => entry.crew),
  };
}
