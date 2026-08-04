import { stat } from "node:fs/promises";
import { boundedProcess } from "../bounded";
import type { Inspection } from "../commands";
import { attempted, noneOf, unreadOf, valueOf } from "./maybe";
import type { Known } from "./maybe";
import { repositoryRoot } from "./paths";
import { redacted } from "./redact";
import type { DiffBase, DiffLine, SessionWorktree, WorktreeFile } from "../interface";

/**
 * Interim source: this repository's worktree list, and the diff of a chosen
 * worktree against its base.
 *
 * Every value is a git fact. The selected worktree must be a member of
 * `git worktree list`, so a crafted value cannot point this at an arbitrary
 * directory. The diff is capped, and a truncated diff says so rather than
 * ending silently on a line that looks like the last one.
 *
 * The base is **resolved, not assumed**. Round-3 QA (#236) found every diff
 * taken against the bare local `main`, which on this checkout was 25 commits
 * behind the trunk: a six-file bugfix rendered as 267 files changed, because
 * everything `main` had gained since the checkout last moved was attributed to
 * the branch under review. This screen exists to separate claimed work from real
 * work, so it prefers the remote-tracking trunk, prints the base's own commit
 * beside the branch's, and — when only a local ref answers — says on the surface
 * that the base may be behind rather than using it quietly.
 */

const DIFF_LINE_CAP = 400;

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

/** One ref this source may diff against, with the commit it resolved to. */
export interface BaseProbe {
  readonly ref: string;
  /**
   * Whether the ref tracks a remote. A local ref moves only when this checkout
   * moves it, so it can sit arbitrarily far behind the trunk while still looking
   * like the trunk — which is exactly how #236 happened.
   */
  readonly tracksRemote: boolean;
  readonly head: Known<string>;
}

/**
 * The base to diff against: the first probe that resolved, preferring one that
 * tracks a remote.
 *
 * A local ref is still used when no remote-tracking ref answered — a checkout
 * with no remote still has a trunk — but it is *labelled* as one that can be
 * behind, so the reader knows the file count may be inflated instead of reading
 * a stale number as the branch's own work.
 */
export function chooseBase(probes: readonly BaseProbe[]): DiffBase {
  const resolved = probes.filter((probe) => probe.head.known === "value");
  const chosen = resolved.find((probe) => probe.tracksRemote) ?? resolved[0];
  if (chosen === undefined) {
    const tried = probes.map((probe) => probe.ref).join(", ");
    const reason =
      probes.length === 0
        ? "no base ref was offered for this worktree"
        : `no base ref resolved in this checkout (tried ${tried})`;
    return { ref: unreadOf(reason), head: unreadOf(reason), note: reason };
  }
  return {
    ref: valueOf(chosen.ref),
    head: chosen.head,
    note: chosen.tracksRemote
      ? `measured against ${chosen.ref}, the trunk as this checkout last fetched it`
      : `measured against the local ref ${chosen.ref}: no remote-tracking trunk resolved here, so this base can sit behind the trunk and this diff can overstate the branch`,
  };
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

/**
 * The refs this source will try, best first, without repeating one.
 *
 * `origin/HEAD` is the checkout's own answer to "what is the trunk"; the literal
 * `origin/main` covers a clone that never had `origin/HEAD` set; the bare local
 * ref is the last resort and is marked as such.
 */
function baseRefs(trunk: Known<string>): readonly (readonly [string, boolean])[] {
  const wanted: readonly (readonly [string, boolean])[] = [
    ...(trunk.known === "value" ? ([[trunk.value.trim(), true]] as const) : []),
    ["origin/main", true],
    ["main", false],
  ];
  const seen = new Set<string>();
  const unique: (readonly [string, boolean])[] = [];
  for (const candidate of wanted) {
    if (candidate[0].length > 0 && !seen.has(candidate[0])) {
      seen.add(candidate[0]);
      unique.push(candidate);
    }
  }
  return unique;
}

async function resolveBase(root: string): Promise<DiffBase> {
  const trunk = await sub(
    { op: "git.trunkRef", root },
    "this checkout records no origin/HEAD to name its trunk"
  );
  const probes = await Promise.all(
    baseRefs(trunk).map(async ([ref, tracksRemote]): Promise<BaseProbe> => {
      const head = await sub(
        { op: "git.refCommit", root, ref },
        `${ref} names no commit in this checkout`
      );
      return {
        ref: redacted(ref),
        tracksRemote,
        ...(head.known === "value" ? { head: valueOf(redacted(head.value.trim())) } : { head }),
      };
    })
  );
  return chooseBase(probes);
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
  const base = await resolveBase(selected);
  // no base means no diff. A read that had nothing to measure against is not a
  // clean tree, so every diff field carries the base's own reason instead
  const baseRef = base.ref.known === "value" ? base.ref.value : null;
  const noBase = (): Known<string> => unreadOf<string>(base.note);
  const stat =
    baseRef === null
      ? noBase()
      : await sub(
          { op: "git.diffStat", root: selected, base: baseRef },
          `nothing differs from ${baseRef}`
        );
  const rawDiff =
    baseRef === null
      ? noBase()
      : await sub(
          { op: "git.diff", root: selected, base: baseRef },
          `nothing differs from ${baseRef}`
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
    baseRef === null
      ? noBase()
      : openPath === null
        ? noneOf<string>(`nothing differs from ${baseRef}`)
        : await sub(
            { op: "git.diffPath", root: selected, base: baseRef, path: openPath },
            `${openPath} does not differ from ${baseRef}`
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
    base,
    files: changed,
    filesRead: stat,
    diff: shown.map((line) => ({ text: redacted(line), kind: classify(line) })),
    diffRead: rawDiff,
    worktrees,
    truncated: lines.length > shown.length,
  };
}
