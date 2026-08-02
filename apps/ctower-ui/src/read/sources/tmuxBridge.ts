import { boundedProcess } from "../bounded";
import { attempted, noneOf, unreadOf, valueOf } from "./maybe";
import type { Known } from "./maybe";
import { carriesRedaction, redacted } from "./redact";
import type {
  LabelledFact,
  SessionStream,
  SessionWorkspace,
  StreamTool,
  StreamTurn,
} from "../interface";

/**
 * Interim source: live tmux sessions, read directly and read-only.
 *
 * Round-1 review of PR #215 found the previous implementation shelling out to
 * Mission Control's `bin/mux list`, which creates a log directory for every row
 * it lists. A read that makes a directory in another repository is not a read.
 * This talks to tmux itself — `list-sessions`, `list-panes`, `capture-pane -p`
 * — which are inspection verbs with no side effect, and it goes through the
 * closed inspection grammar so no other verb is expressible.
 *
 * Every string reaching a screen passes `redacted` first: a pane is whatever a
 * seat has on screen right now, and a session name or working directory is no
 * safer than the pane body.
 */

const PANE_LINES = 120;
const TURN_OPENER = /^[●✻✽·⏺*]/u;
const TOOL_OPENER = /^[•↳⎿]/u;
const TOOL_CONTINUATION = /^[└│]/u;
const CHROME = /^[─━]{6,}\s*$|^\s*⏵⏵|^\s*❯\s*$|^\s*←\s+for agents/u;

interface Session {
  readonly name: string;
  readonly cwd: Known<string>;
  readonly command: Known<string>;
}

function fact(label: string, value: Known<string>, detail: string | null): LabelledFact {
  return {
    label,
    value: value.known === "value" ? valueOf(redacted(value.value)) : value,
    detail: detail === null ? null : redacted(detail),
  };
}

async function sessions(): Promise<readonly Session[]> {
  const names = (await boundedProcess({ op: "tmux.sessions" }))
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  const panes = await attempted(
    async () => await boundedProcess({ op: "tmux.panes" }),
    (text) => text.trim().length === 0,
    "tmux reported no pane for any session"
  );
  const byName = new Map<string, { cwd: string; command: string }>();
  if (panes.known === "value") {
    for (const line of panes.value.split("\n")) {
      const [name, cwd, command] = line.split("\t");
      if (name !== undefined && cwd !== undefined && command !== undefined && !byName.has(name)) {
        byName.set(name, { cwd, command });
      }
    }
  }
  return names.map((name): Session => {
    const pane = byName.get(name);
    if (pane !== undefined) {
      return { name, cwd: valueOf(pane.cwd), command: valueOf(pane.command) };
    }
    // a pane listing that failed is not a session without a directory
    return panes.known === "unread"
      ? { name, cwd: unreadOf(panes.reason), command: unreadOf(panes.reason) }
      : {
          name,
          cwd: noneOf("tmux lists no pane for this session"),
          command: noneOf("tmux lists no pane for this session"),
        };
  });
}

function chosen(all: readonly Session[], requested: string | null): Session | null {
  return all.find((session) => session.name === requested) ?? all[0] ?? null;
}

function turnsOf(lines: readonly string[]): readonly StreamTurn[] {
  const turns: StreamTurn[] = [];
  let current: StreamTurn = { body: [], tools: [] };
  let toolIndent: number | null = null;
  const indentOf = (line: string): number => line.length - line.trimStart().length;
  const close = (): void => {
    if (current.body.length > 0 || current.tools.length > 0) {
      turns.push(current);
    }
    current = { body: [], tools: [] };
  };
  for (const line of lines) {
    if (CHROME.test(line)) {
      continue;
    }
    if (TOOL_OPENER.test(line.trimStart())) {
      toolIndent = indentOf(line);
      const tool: StreamTool = {
        summary: line.trimStart().replace(TOOL_OPENER, "").trim(),
        output: [line],
      };
      current = { ...current, tools: [...current.tools, tool] };
      continue;
    }
    const open = current.tools.at(-1);
    if (
      toolIndent !== null &&
      open !== undefined &&
      line.trim().length > 0 &&
      (indentOf(line) > toolIndent || TOOL_CONTINUATION.test(line.trimStart()))
    ) {
      current = {
        ...current,
        tools: [...current.tools.slice(0, -1), { ...open, output: [...open.output, line] }],
      };
      continue;
    }
    toolIndent = null;
    if (line.trim().length === 0) {
      continue;
    }
    if (
      TURN_OPENER.test(line.trimStart()) &&
      (current.body.length > 0 || current.tools.length > 0)
    ) {
      close();
    }
    current = { ...current, body: [...current.body, line] };
  }
  close();
  return turns;
}

export async function readSessionStream(requested: string | null): Promise<SessionStream> {
  const all = await sessions();
  const session = chosen(all, requested);
  if (session === null) {
    throw new Error("tmux lists no session on this host");
  }
  const raw = (
    await boundedProcess({ op: "tmux.capture", session: session.name, lines: PANE_LINES })
  ).split("\n");
  const lines = raw.map(redacted);
  const turns = turnsOf(lines).map((turn) => ({
    body: turn.body,
    tools: turn.tools.map((tool) => ({ summary: redacted(tool.summary), output: tool.output })),
  }));
  return {
    chosen: redacted(session.name),
    choices: all.map((entry) => redacted(entry.name)),
    header: [
      fact("session", valueOf(session.name), null),
      fact("running", session.command, null),
      fact("directory", session.cwd, null),
    ],
    turns,
    rawLines: lines,
    observedAt: new Date().toISOString(),
    wasRedacted:
      raw.some(carriesRedaction) ||
      all.some((entry) => carriesRedaction(entry.name)) ||
      (session.cwd.known === "value" && carriesRedaction(session.cwd.value)),
    fidelityNote:
      "a terminal capture, not a recorded turn stream — the reasoning, tool arguments and token cost of a turn are session facts ctower does not record yet",
  };
}

export async function readSessionWorkspace(requested: string | null): Promise<SessionWorkspace> {
  const all = await sessions();
  const session = chosen(all, requested);
  if (session === null) {
    throw new Error("tmux lists no session on this host");
  }
  const inRepository = async (
    inspect: () => Promise<string>,
    why: string
  ): Promise<Known<string>> =>
    session.cwd.known === "value"
      ? await attempted(inspect, (text) => text.trim().length === 0, why)
      : session.cwd;
  const root = session.cwd.known === "value" ? session.cwd.value : "";
  const branch = await inRepository(
    async () => (await boundedProcess({ op: "git.branch", root })).trim(),
    "this directory is not a git checkout"
  );
  const head = await inRepository(
    async () => (await boundedProcess({ op: "git.revision", root })).trim(),
    "this directory is not a git checkout"
  );
  const subject = await inRepository(
    async () => (await boundedProcess({ op: "git.headSubject", root })).trim(),
    "no commit subject is recorded"
  );
  const toplevel = await inRepository(
    async () => (await boundedProcess({ op: "git.toplevel", root })).trim(),
    "this directory is not a git checkout"
  );

  return {
    chosen: redacted(session.name),
    choices: all.map((entry) => redacted(entry.name)),
    facts: [
      fact("Session", valueOf(session.name), "as tmux names it"),
      fact("Directory", session.cwd, "the pane's working directory"),
      fact("Running", session.command, "the process in the pane"),
      fact("Repository", toplevel, null),
      fact("Branch", branch, subject.known === "value" ? subject.value : null),
      fact("Head", head, null),
    ],
    startCommand: noneOf(
      "how this session was started is not recorded; the surface refuses to reconstruct a command it did not observe"
    ),
    sourceNote: "live tmux sessions, read-only",
  };
}
