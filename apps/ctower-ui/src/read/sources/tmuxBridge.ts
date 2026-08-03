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
const TURN_OPENER = /^[●·⏺*]/u;
/**
 * The source's own status glyphs — a spinner tick, an elapsed-time counter, a
 * scheduled-wake announcement. Round-3 QA (#242) found five of eleven bubbles on
 * one screenful of `commander` carrying nothing but these: *Churned for 52s*,
 * *Running scheduled task*, *Ran 2 shell commands*. They are attached to the
 * turn they interrupt instead of being promoted to turns of their own, which is
 * what "tool calls collapse into the flow" describes.
 */
const STATUS_OPENER = /^[✻✽]/u;
const TOOL_OPENER = /^[•↳⎿]/u;
const TOOL_CONTINUATION = /^[└│]/u;
const CHROME = /^[─━]{6,}\s*$|^\s*⏵⏵|^\s*❯\s*$|^\s*←\s+for agents/u;

interface Session {
  readonly name: string;
  readonly cwd: Known<string>;
  readonly command: Known<string>;
  /** The column this session wrapped its own prose at, when tmux reported one. */
  readonly width: number | null;
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
  const byName = new Map<string, { cwd: string; command: string; width: number | null }>();
  if (panes.known === "value") {
    for (const line of panes.value.split("\n")) {
      const [name, cwd, command, width] = line.split("\t");
      if (name !== undefined && cwd !== undefined && command !== undefined && !byName.has(name)) {
        const columns = Number.parseInt(width ?? "", 10);
        byName.set(name, {
          cwd,
          command,
          width: Number.isInteger(columns) && columns > 0 ? columns : null,
        });
      }
    }
  }
  return names.map((name): Session => {
    const pane = byName.get(name);
    if (pane !== undefined) {
      return {
        name,
        cwd: valueOf(pane.cwd),
        command: valueOf(pane.command),
        width: pane.width,
      };
    }
    // a pane listing that failed is not a session without a directory
    return panes.known === "unread"
      ? {
          name,
          cwd: unreadOf(panes.reason),
          command: unreadOf(panes.reason),
          width: null,
        }
      : {
          name,
          cwd: noneOf("tmux lists no pane for this session"),
          command: noneOf("tmux lists no pane for this session"),
          width: null,
        };
  });
}

function chosen(all: readonly Session[], requested: string | null): Session | null {
  return all.find((session) => session.name === requested) ?? all[0] ?? null;
}

/**
 * The pane's own left padding, removed from a turn's body.
 *
 * The TUI indents its prose by two columns. That padding is chrome, not content,
 * and inside a 370px bubble it reads as a hanging indent on every line (#242).
 * Only the *common* indent goes: a line the seat indented further than its
 * neighbours keeps the difference, so a quoted block or a list stays shaped.
 */
export function unindent(body: readonly string[]): readonly string[] {
  const filled = body.filter((line) => line.trim().length > 0);
  if (filled.length === 0) {
    return body;
  }
  const shared = Math.min(...filled.map((line) => line.length - line.trimStart().length));
  return shared === 0 ? body : body.map((line) => line.slice(shared));
}

/**
 * How close to the wrap column a line has to reach to count as wrapped.
 *
 * The session soft-wraps at word boundaries and the capture strips the trailing
 * space, so a wrapped line stops one word short of the column rather than at it.
 * Measured on this host at width 142, wrapped lines land at 134–142; a paragraph
 * that simply ended landed at 33. Sixteen columns is wider than the longest word
 * that gets pushed and far narrower than that gap.
 */
const WRAP_SLACK = 16;

/**
 * A paragraph put back together from the lines the session wrapped it into.
 *
 * This is a **reconstruction**, and the surface says so in its fidelity note. The
 * capture has no wrap markers to read: round-3 QA (#242) traced the hanging
 * indent to the session emitting its own newlines at ~135–140 columns, which
 * `capture-pane -J` cannot rejoin because the terminal grid never wrapped. So the
 * rule is stated rather than hidden — a line that reached the pane's wrap column
 * is joined to the next non-empty one, with the space the wrap consumed put back.
 *
 * A line that ends well short of the column ends its paragraph, which is why an
 * unrelated `column` (a stream with no wrapping) leaves the body untouched.
 */
export function rejoined(body: readonly string[], column: number | null): readonly string[] {
  if (column === null || column <= WRAP_SLACK) {
    return body;
  }
  const joined: string[] = [];
  for (const line of body) {
    const previous = joined.at(-1);
    const wrapped = previous !== undefined && previous.length >= column - WRAP_SLACK;
    if (wrapped && line.trim().length > 0) {
      joined[joined.length - 1] = `${previous.trimEnd()} ${line.trimStart()}`;
      continue;
    }
    joined.push(line);
  }
  return joined;
}

export function turnsOf(
  lines: readonly string[],
  column: number | null = null
): readonly StreamTurn[] {
  const turns: StreamTurn[] = [];
  let current: StreamTurn = { body: [], tools: [], notes: [] };
  let toolIndent: number | null = null;
  const indentOf = (line: string): number => line.length - line.trimStart().length;
  const empty = (turn: StreamTurn): boolean =>
    turn.body.length === 0 && turn.tools.length === 0 && turn.notes.length === 0;
  const close = (): void => {
    if (!empty(current)) {
      // the padding goes first: the wrap column is measured on the padded line,
      // so the reconstruction is done against the width the session actually had
      const unpadded = unindent(current.body);
      const padding = (current.body[0]?.length ?? 0) - (unpadded[0]?.length ?? 0);
      turns.push({
        ...current,
        body: rejoined(unpadded, column === null ? null : column - padding),
      });
    }
    current = { body: [], tools: [], notes: [] };
  };
  for (const line of lines) {
    if (CHROME.test(line)) {
      continue;
    }
    if (STATUS_OPENER.test(line.trimStart())) {
      // a status line never opens a turn. It joins the one it interrupts, or —
      // when nothing is open — the one before it, so a screenful of spinner
      // ticks cannot become a screenful of empty bubbles
      const note = line.trim();
      if (empty(current) && turns.length > 0) {
        const previous = turns[turns.length - 1];
        if (previous !== undefined) {
          turns[turns.length - 1] = { ...previous, notes: [...previous.notes, note] };
          continue;
        }
      }
      current = { ...current, notes: [...current.notes, note] };
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
  const turns = turnsOf(lines, session.width).map((turn) => ({
    body: turn.body,
    tools: turn.tools.map((tool) => ({ summary: redacted(tool.summary), output: tool.output })),
    notes: turn.notes.map(redacted),
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
      session.width === null
        ? "a terminal capture, not a recorded turn stream — the reasoning, tool arguments and token cost of a turn are session facts ctower does not record yet. tmux reported no pane width, so the session's own line breaks are shown as captured"
        : `a terminal capture, not a recorded turn stream — the reasoning, tool arguments and token cost of a turn are session facts ctower does not record yet. The session wrapped its prose at ${session.width.toString()} columns and the capture carries no wrap markers, so a line reaching that column is rejoined to the next: the paragraphs here are reconstructed, not quoted line for line. The raw view is the capture as it arrived`,
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
