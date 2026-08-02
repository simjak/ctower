/**
 * Every child process this surface may run, as a closed grammar.
 *
 * Round-1 review of PR #215 found the previous boundary checking only the
 * command *basename* and then handing the caller's own argv to `execFile`.
 * `shell: false` stops interpolation; it does not stop `git reset`,
 * `systemctl stop` or `crontab <file>`. A read-only guarantee that depends on
 * every caller passing harmless arguments is not a guarantee.
 *
 * So callers no longer supply argv. They name an inspection, and this module
 * builds the argv — the value slots are the only thing they control, and each
 * is validated. A mutating subcommand cannot be expressed by this type, which
 * is the point: the guarantee is structural, not conventional.
 *
 * The tools are resolved to absolute paths from a fixed table rather than
 * looked up on `PATH`, so a directory earlier on `PATH` cannot substitute a
 * different binary.
 *
 * This module is pure and dependency-free at runtime, so
 * `tests/repository/test_inspection_grammar.py` executes it directly and drives
 * the accepted argv for every operation the union declares, the refusal owed by
 * every value slot, and the absolute-path resolution above.
 */

export type Tool = "git" | "crontab" | "systemctl" | "tmux";

const DEFAULT_EXECUTABLES: Readonly<Record<Tool, string>> = {
  git: "/usr/bin/git",
  crontab: "/usr/bin/crontab",
  systemctl: "/usr/bin/systemctl",
  tmux: "/usr/bin/tmux",
};

export class InspectionRefused extends Error {
  public constructor(detail: string) {
    super(detail);
    this.name = "InspectionRefused";
  }
}

export type Inspection =
  | { readonly op: "git.revision"; readonly root: string }
  | { readonly op: "git.trunkRef"; readonly root: string }
  | { readonly op: "git.branch"; readonly root: string }
  | { readonly op: "git.headSubject"; readonly root: string }
  | { readonly op: "git.toplevel"; readonly root: string }
  | { readonly op: "git.tree"; readonly root: string; readonly revision: string }
  | {
      readonly op: "git.show";
      readonly root: string;
      readonly revision: string;
      readonly path: string;
    }
  | { readonly op: "git.pathLog"; readonly root: string; readonly path: string }
  | {
      readonly op: "git.trunkLog";
      readonly root: string;
      readonly ref: string;
      readonly days: number;
    }
  | { readonly op: "git.worktrees"; readonly root: string }
  | { readonly op: "git.diffStat"; readonly root: string; readonly base: string }
  | { readonly op: "git.diff"; readonly root: string; readonly base: string }
  | {
      readonly op: "git.diffPath";
      readonly root: string;
      readonly base: string;
      readonly path: string;
    }
  | { readonly op: "crontab.list" }
  | { readonly op: "systemd.timers" }
  | { readonly op: "tmux.sessions" }
  | { readonly op: "tmux.panes" }
  | { readonly op: "tmux.capture"; readonly session: string; readonly lines: number };

export interface Invocation {
  readonly tool: Tool;
  readonly executable: string;
  readonly args: readonly string[];
  readonly maxBytes: number;
  /** A label for logs and failures; never used to build the command. */
  readonly label: string;
}

/** A value slot may not become an option, a traversal, or a separator. */
function value(text: string, slot: string): string {
  if (text.length === 0 || text.length > 512) {
    throw new InspectionRefused(`${slot} is empty or too long`);
  }
  if (text.startsWith("-")) {
    throw new InspectionRefused(`${slot} may not begin with '-': it would parse as an option`);
  }
  if (text.includes("\0") || text.includes("\n")) {
    throw new InspectionRefused(`${slot} carries a control character`);
  }
  return text;
}

/** A ref or revision: no options, no path traversal, no refspec punctuation. */
function ref(text: string, slot: string): string {
  const checked = value(text, slot);
  if (!/^[A-Za-z0-9._/@-]+$/u.test(checked) || checked.includes("..")) {
    throw new InspectionRefused(`${slot} is not a plain ref`);
  }
  return checked;
}

/** A repository-relative path: never absolute, never escaping the tree. */
function repoPath(text: string, slot: string): string {
  const checked = value(text, slot);
  if (checked.startsWith("/") || checked.split("/").includes("..")) {
    throw new InspectionRefused(`${slot} must stay inside the tree`);
  }
  return checked;
}

function count(number: number, slot: string, ceiling: number): string {
  if (!Number.isInteger(number) || number < 1 || number > ceiling) {
    throw new InspectionRefused(`${slot} is not a bounded positive integer`);
  }
  return number.toString();
}

function executableFor(tool: Tool): string {
  const override = process.env[`CTOWER_UI_EXEC_${tool.toUpperCase()}`];
  const resolved = override === undefined || override === "" ? DEFAULT_EXECUTABLES[tool] : override;
  if (!resolved.startsWith("/")) {
    throw new InspectionRefused(`${tool} must resolve to an absolute path, not a PATH lookup`);
  }
  return resolved;
}

function git(root: string, args: readonly string[], label: string, maxBytes = 400_000): Invocation {
  return {
    tool: "git",
    executable: executableFor("git"),
    args: ["-C", value(root, "repository root"), ...args],
    maxBytes,
    label,
  };
}

/**
 * Build the argv for one inspection. Every branch is a fixed verb list; the
 * caller's values reach only the slots validated above.
 */
export function invocationFor(inspection: Inspection): Invocation {
  switch (inspection.op) {
    case "git.revision":
      return git(inspection.root, ["rev-parse", "--short=8", "HEAD"], inspection.op);
    case "git.trunkRef":
      return git(
        inspection.root,
        ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
        inspection.op
      );
    case "git.branch":
      return git(inspection.root, ["rev-parse", "--abbrev-ref", "HEAD"], inspection.op);
    case "git.headSubject":
      return git(inspection.root, ["log", "-1", "--format=%s"], inspection.op);
    case "git.toplevel":
      return git(inspection.root, ["rev-parse", "--show-toplevel"], inspection.op);
    case "git.tree":
      return git(
        inspection.root,
        ["ls-tree", "-r", "--name-only", ref(inspection.revision, "revision")],
        inspection.op,
        2_000_000
      );
    case "git.show":
      return git(
        inspection.root,
        ["show", `${ref(inspection.revision, "revision")}:${repoPath(inspection.path, "path")}`],
        inspection.op
      );
    case "git.pathLog":
      return git(
        inspection.root,
        [
          "log",
          "-n",
          "5",
          "--format=%h%x1f%s%x1f%an%x1f%aI",
          "--",
          repoPath(inspection.path, "path"),
        ],
        inspection.op
      );
    case "git.trunkLog":
      return git(
        inspection.root,
        [
          "log",
          "--first-parent",
          ref(inspection.ref, "ref"),
          `--since=${count(inspection.days, "days", 400)} days ago`,
          "--format=%aI%x1f%s",
        ],
        inspection.op,
        2_000_000
      );
    case "git.worktrees":
      return git(inspection.root, ["worktree", "list", "--porcelain"], inspection.op);
    case "git.diffStat":
      return git(
        inspection.root,
        ["diff", "--numstat", `${ref(inspection.base, "base")}...HEAD`],
        inspection.op,
        2_000_000
      );
    case "git.diff":
      return git(
        inspection.root,
        ["diff", `${ref(inspection.base, "base")}...HEAD`],
        inspection.op,
        2_000_000
      );
    case "git.diffPath":
      return git(
        inspection.root,
        ["diff", `${ref(inspection.base, "base")}...HEAD`, "--", repoPath(inspection.path, "path")],
        inspection.op,
        2_000_000
      );
    case "crontab.list":
      return {
        tool: "crontab",
        executable: executableFor("crontab"),
        args: ["-l"],
        maxBytes: 200_000,
        label: inspection.op,
      };
    case "systemd.timers":
      return {
        tool: "systemctl",
        executable: executableFor("systemctl"),
        args: ["--user", "list-timers", "--all", "--output=json"],
        maxBytes: 400_000,
        label: inspection.op,
      };
    case "tmux.sessions":
      return {
        tool: "tmux",
        executable: executableFor("tmux"),
        args: ["list-sessions", "-F", "#{session_name}"],
        maxBytes: 200_000,
        label: inspection.op,
      };
    case "tmux.panes":
      return {
        tool: "tmux",
        executable: executableFor("tmux"),
        args: [
          "list-panes",
          "-a",
          "-F",
          "#{session_name}\t#{pane_current_path}\t#{pane_current_command}",
        ],
        maxBytes: 400_000,
        label: inspection.op,
      };
    case "tmux.capture":
      return {
        tool: "tmux",
        executable: executableFor("tmux"),
        args: [
          "capture-pane",
          "-p",
          "-t",
          value(inspection.session, "session"),
          "-S",
          `-${count(inspection.lines, "lines", 2_000)}`,
        ],
        maxBytes: 400_000,
        label: inspection.op,
      };
  }
}
