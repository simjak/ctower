// Drivers for the closed inspection grammar at the child-process boundary.
//
// Round-1 review of PR #215 found that boundary checking only a command
// basename and then running the caller's own argv; the repair replaced it with
// a named `Inspection` whose argv this module builds. Round-2 found the repair's
// docblock citing a grammar test that did not exist, leaving the value-slot
// validators — the things that stand between a reader-supplied string and
// `git --upload-pack=…`, `HEAD:../../etc/shadow` or `crontab <file>` — asserted
// only by inspection.
//
// So this drives the real function: every accepted inspection's argv, every
// rejection the validators owe, and the absolute-path resolution that stops a
// planted directory on PATH from substituting a binary.
//
// `commands.ts` is pure and dependency-free at runtime, so Node executes it
// directly with type stripping — no bundler, no network, no live state, no
// clock, no child process actually spawned. Nothing here runs a command; it
// only asks what command would be run.

import { InspectionRefused, invocationFor } from "../../apps/ctower-ui/src/read/commands.ts";
import type { Inspection, Invocation } from "../../apps/ctower-ui/src/read/commands.ts";

const ROOT = "/srv/projects/ctower";

/** One inspection per member of the union, with values a screen really passes. */
const ACCEPTED: readonly Inspection[] = [
  { op: "git.revision", root: ROOT },
  { op: "git.trunkRef", root: ROOT },
  { op: "git.branch", root: ROOT },
  { op: "git.headSubject", root: ROOT },
  { op: "git.toplevel", root: ROOT },
  { op: "git.tree", root: ROOT, revision: "HEAD" },
  { op: "git.show", root: ROOT, revision: "HEAD", path: "docs/CODING_STANDARDS.md" },
  { op: "git.pathLog", root: ROOT, path: "docs/CODING_STANDARDS.md" },
  { op: "git.trunkLog", root: ROOT, ref: "origin/main", days: 30 },
  { op: "git.worktrees", root: ROOT },
  { op: "git.diffStat", root: ROOT, base: "origin/main" },
  { op: "git.diff", root: ROOT, base: "origin/main" },
  { op: "git.diffPath", root: ROOT, base: "origin/main", path: "SPEC.md" },
  { op: "crontab.list" },
  { op: "systemd.timers" },
  { op: "tmux.sessions" },
  { op: "tmux.crews" },
  { op: "tmux.panes" },
  { op: "tmux.capture", session: "designer-r2710-ui-build", lines: 120 },
];

interface Refusal {
  readonly slot: string;
  readonly refused: boolean;
  readonly kind: string;
  readonly message: string;
  readonly argv: readonly string[] | null;
}

/**
 * Build one inspection that must be refused. A build that succeeds is reported
 * with the argv it would have produced, so a regression names the command that
 * escaped rather than only the assertion that failed.
 */
function refusalOf(slot: string, build: () => Invocation): Refusal {
  try {
    const invocation = build();
    return {
      slot,
      refused: false,
      kind: "none",
      message: "the grammar accepted this value",
      argv: [invocation.executable, ...invocation.args],
    };
  } catch (error) {
    return {
      slot,
      refused: error instanceof InspectionRefused,
      kind: error instanceof Error ? error.name : typeof error,
      message: error instanceof Error ? error.message : String(error),
      argv: null,
    };
  }
}

const accepted: Record<string, unknown> = {};
for (const inspection of ACCEPTED) {
  const invocation = invocationFor(inspection);
  accepted[inspection.op] = {
    tool: invocation.tool,
    executable: invocation.executable,
    args: invocation.args,
    label: invocation.label,
    maxBytes: invocation.maxBytes,
  };
}

const rejected: readonly Refusal[] = [
  // ---- value(): the slot that every other validator is built on ----
  refusalOf("value/empty", () => invocationFor({ op: "git.branch", root: "" })),
  refusalOf("value/too-long", () =>
    invocationFor({ op: "git.branch", root: `/${"a".repeat(600)}` })
  ),
  // a root that parses as an option is how `git` is talked into running a
  // program of the caller's choosing
  refusalOf("value/leading-dash", () =>
    invocationFor({ op: "git.branch", root: "--exec-path=/tmp/planted" })
  ),
  refusalOf("value/newline", () =>
    invocationFor({ op: "git.branch", root: "/srv/projects/ctower\nreset --hard" })
  ),
  refusalOf("value/nul", () =>
    invocationFor({ op: "git.branch", root: "/srv/projects/ctower\u0000" })
  ),
  refusalOf("value/session-leading-dash", () =>
    invocationFor({ op: "tmux.capture", session: "-S", lines: 10 })
  ),

  // ---- ref(): a revision may not smuggle punctuation or a range ----
  refusalOf("ref/shell-punctuation", () =>
    invocationFor({ op: "git.diff", root: ROOT, base: "main; rm -rf /" })
  ),
  refusalOf("ref/space", () => invocationFor({ op: "git.tree", root: ROOT, revision: "HEAD x" })),
  refusalOf("ref/double-dot", () =>
    invocationFor({ op: "git.diff", root: ROOT, base: "origin/main..HEAD" })
  ),
  refusalOf("ref/traversal", () =>
    invocationFor({ op: "git.trunkLog", root: ROOT, ref: "refs/heads/../../evil", days: 7 })
  ),
  refusalOf("ref/leading-dash", () =>
    invocationFor({ op: "git.tree", root: ROOT, revision: "--output=/tmp/planted" })
  ),

  // ---- repoPath(): the reader-supplied path is the classic traversal ----
  refusalOf("repoPath/absolute", () =>
    invocationFor({ op: "git.show", root: ROOT, revision: "HEAD", path: "/etc/shadow" })
  ),
  refusalOf("repoPath/traversal", () =>
    invocationFor({ op: "git.show", root: ROOT, revision: "HEAD", path: "../../etc/shadow" })
  ),
  refusalOf("repoPath/interior-traversal", () =>
    invocationFor({ op: "git.diffPath", root: ROOT, base: "main", path: "src/../../outside" })
  ),
  refusalOf("repoPath/leading-dash", () =>
    invocationFor({ op: "git.pathLog", root: ROOT, path: "--output=/tmp/planted" })
  ),

  // ---- count(): an unbounded number is an unbounded read ----
  refusalOf("count/zero", () => invocationFor({ op: "tmux.capture", session: "crew", lines: 0 })),
  refusalOf("count/negative", () =>
    invocationFor({ op: "tmux.capture", session: "crew", lines: -50 })
  ),
  refusalOf("count/fractional", () =>
    invocationFor({ op: "tmux.capture", session: "crew", lines: 1.5 })
  ),
  refusalOf("count/over-ceiling", () =>
    invocationFor({ op: "tmux.capture", session: "crew", lines: 20_000 })
  ),
  refusalOf("count/days-over-ceiling", () =>
    invocationFor({ op: "git.trunkLog", root: ROOT, ref: "main", days: 4_000 })
  ),
];

// ---- absolute-path resolution ----
//
// The tools resolve from a fixed table. An override is honoured only when it is
// itself absolute, so no environment can turn a tool into a PATH lookup.
const resolution: Record<string, unknown> = {
  defaults: Object.fromEntries(
    ACCEPTED.map((inspection) => {
      const invocation = invocationFor(inspection);
      return [invocation.tool, invocation.executable];
    })
  ),
};

process.env.CTOWER_UI_EXEC_TMUX = "/opt/planted/bin/tmux";
resolution.absoluteOverrideHonoured = invocationFor({ op: "tmux.sessions" }).executable;
process.env.CTOWER_UI_EXEC_TMUX = "";
resolution.emptyOverrideFallsBackToTable = invocationFor({ op: "tmux.sessions" }).executable;
delete process.env.CTOWER_UI_EXEC_TMUX;

process.env.CTOWER_UI_EXEC_GIT = "git";
resolution.bareNameOverride = refusalOf("resolution/path-lookup", () =>
  invocationFor({ op: "git.branch", root: ROOT })
);
process.env.CTOWER_UI_EXEC_GIT = "./tools/git";
resolution.relativeOverride = refusalOf("resolution/relative", () =>
  invocationFor({ op: "git.branch", root: ROOT })
);
delete process.env.CTOWER_UI_EXEC_GIT;

process.stdout.write(JSON.stringify({ accepted, rejected, resolution }, null, 2));
