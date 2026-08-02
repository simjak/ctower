import { boundedProcess } from "../bounded";
import { repositoryRoot } from "./paths";
import { redacted } from "./redact";
import type { DiffLine, SessionWorktree, WorktreeFile } from "../interface";

/**
 * Interim source: this repository's worktree list, and the diff of a chosen
 * worktree against its base.
 *
 * Every value is a git fact. The selected worktree must be a member of
 * `git worktree list`, so a crafted value cannot point this at an arbitrary
 * directory. The diff is capped, and a truncated diff says so rather than
 * ending silently on a line that looks like the last one.
 */

const DIFF_LINE_CAP = 400;
const BASE = "main";

function porcelainWorktrees(text: string): readonly string[] {
  return text
    .split("\n")
    .filter((line) => line.startsWith("worktree "))
    .map((line) => line.slice("worktree ".length).trim())
    .filter((line) => line.length > 0);
}

function numstat(text: string): readonly WorktreeFile[] {
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .flatMap((line) => {
      const [added, removed, path] = line.split("\t");
      if (path === undefined || added === undefined || removed === undefined) {
        return [];
      }
      const parse = (value: string): number | null =>
        value === "-" ? null : Number.isInteger(Number(value)) ? Number(value) : null;
      return [{ path, status: "changed", added: parse(added), removed: parse(removed) }];
    });
}

function classify(line: string): DiffLine["kind"] {
  if (line.startsWith("diff --git") || line.startsWith("+++") || line.startsWith("---")) {
    return "file";
  }
  if (line.startsWith("@@")) {
    return "hunk";
  }
  if (line.startsWith("+")) {
    return "add";
  }
  if (line.startsWith("-")) {
    return "del";
  }
  return "context";
}

async function tryText(command: string, args: readonly string[]): Promise<string> {
  try {
    return await boundedProcess({ command, args, maxBytes: 2_000_000 });
  } catch {
    // a worktree with no base to compare against is a real answer, not a failure
    return "";
  }
}

export async function readSessionWorktree(requested: string | null): Promise<SessionWorktree> {
  const root = repositoryRoot();
  const listing = await boundedProcess({
    command: "git",
    args: ["-C", root, "worktree", "list", "--porcelain"],
  });
  const worktrees = porcelainWorktrees(listing);
  // this screen is the *session's* worktree, so the default is the one this app
  // is served from when git lists it; otherwise the repository's first entry
  const served = worktrees.find((path) => path === root);
  const selected =
    requested !== null && worktrees.includes(requested)
      ? requested
      : (served ?? worktrees[0] ?? root);

  const branch = (
    await tryText("git", ["-C", selected, "rev-parse", "--abbrev-ref", "HEAD"])
  ).trim();
  const head = (await tryText("git", ["-C", selected, "rev-parse", "--short=8", "HEAD"])).trim();
  const files = numstat(
    await tryText("git", ["-C", selected, "diff", "--numstat", `${BASE}...HEAD`])
  );
  const rawDiff = await tryText("git", ["-C", selected, "diff", `${BASE}...HEAD`]);
  const lines = rawDiff.split("\n").filter((line) => line.length > 0);
  const shown = lines.slice(0, DIFF_LINE_CAP);

  return {
    root: selected,
    branch: branch.length === 0 ? null : branch,
    head: head.length === 0 ? null : head,
    base: BASE,
    files,
    diff: shown.map((line) => ({ text: redacted(line), kind: classify(line) })),
    worktrees,
    truncated: lines.length > shown.length,
  };
}
