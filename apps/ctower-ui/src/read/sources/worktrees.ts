import { stat } from "node:fs/promises";
import { boundedProcess } from "../bounded";
import type { Inspection } from "../commands";
import { attempted, noneOf } from "./maybe";
import type { Known } from "./maybe";
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

/**
 * A sub-read that keeps its own availability. Round-1 review found this
 * swallowing every git failure into an empty string, which the screen then
 * rendered as "no file differs" — a failed read painted as a clean tree.
 */
async function sub(inspection: Inspection, why: string): Promise<Known<string>> {
  return await attempted(
    async () => await boundedProcess(inspection),
    (text) => text.trim().length === 0,
    why
  );
}

/** A worktree whose directory is gone was reaped; git still lists it. */
async function onDisk(paths: readonly string[]): Promise<readonly string[]> {
  const checked = await Promise.all(
    paths.map(async (path) => {
      try {
        return (await stat(path)).isDirectory() ? path : null;
      } catch {
        return null;
      }
    })
  );
  return checked.filter((path): path is string => path !== null);
}

export async function readSessionWorktree(
  requested: string | null,
  requestedPath: string | null = null
): Promise<SessionWorktree> {
  const root = repositoryRoot();
  const listing = await boundedProcess({ op: "git.worktrees", root });
  const listed = porcelainWorktrees(listing);
  const worktrees = await onDisk(listed);
  const reaped = listed.length - worktrees.length;
  // this screen is the *session's* worktree, so the default is the one this app
  // is served from when git lists it; otherwise the repository's first entry
  const served = worktrees.find((path) => path === root);
  const selected =
    requested !== null && worktrees.includes(requested)
      ? requested
      : (served ?? worktrees[0] ?? root);

  const branch = await sub({ op: "git.branch", root: selected }, "no branch is checked out here");
  const head = await sub({ op: "git.revision", root: selected }, "no commit is checked out here");
  const stat = await sub(
    { op: "git.diffStat", root: selected, base: BASE },
    `nothing differs from ${BASE}`
  );
  const rawDiff = await sub(
    { op: "git.diff", root: selected, base: BASE },
    `nothing differs from ${BASE}`
  );
  const lines =
    rawDiff.known === "value" ? rawDiff.value.split("\n").filter((line) => line.length > 0) : [];
  const shown = lines.slice(0, DIFF_LINE_CAP);
  const changed = stat.known === "value" ? numstat(stat.value) : [];

  const openPath =
    requestedPath !== null && changed.some((file) => file.path === requestedPath)
      ? requestedPath
      : (changed[0]?.path ?? null);
  const pathDiff: Known<string> =
    openPath === null
      ? noneOf<string>(`nothing differs from ${BASE}`)
      : await sub(
          { op: "git.diffPath", root: selected, base: BASE, path: openPath },
          `${openPath} does not differ from ${BASE}`
        );
  const pathLines =
    pathDiff.known === "value" ? pathDiff.value.split("\n").filter((line) => line.length > 0) : [];

  return {
    root: selected,
    reaped,
    openPath,
    openDiff: pathLines.slice(0, DIFF_LINE_CAP).map((line) => ({
      text: redacted(line),
      kind: classify(line),
    })),
    openDiffRead: pathDiff,
    branch: { ...branch, ...(branch.known === "value" ? { value: branch.value.trim() } : {}) },
    head: { ...head, ...(head.known === "value" ? { value: head.value.trim() } : {}) },
    base: BASE,
    files: changed,
    filesRead: stat,
    diff: shown.map((line) => ({ text: redacted(line), kind: classify(line) })),
    diffRead: rawDiff,
    worktrees,
    truncated: lines.length > shown.length,
  };
}
