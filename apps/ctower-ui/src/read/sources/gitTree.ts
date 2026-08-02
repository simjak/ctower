import { boundedProcess } from "../bounded";
import { filesRoot } from "./paths";
import { redacted } from "./redact";
import type { AuthoredFiles, CommitLine, TreeEntry } from "../interface";

/**
 * Interim source: the git tree of the repository the Files screen browses.
 *
 * Browsing only. The path a reader opens is checked against the tree listing
 * before it is used, so a crafted path cannot walk out of the repository, and
 * the file is read with `git show <rev>:<path>` rather than from the working
 * tree — a committed revision, not whatever a concurrent worktree happens to
 * have on disk. Editing stays visibly read-only v1; nothing here writes.
 */

const UNIT_SEPARATOR = "\u001f";
const TREE_CAP = 400;
const LINE_CAP = 400;

function depthOf(path: string): number {
  return path.split("/").length - 1;
}

/** Expand a file list into the directory rows a tree needs, in path order. */
function treeOf(paths: readonly string[]): readonly TreeEntry[] {
  const rows = new Map<string, TreeEntry>();
  for (const path of paths) {
    const parts = path.split("/");
    for (let index = 1; index < parts.length; index += 1) {
      const directory = parts.slice(0, index).join("/");
      rows.set(directory, { path: directory, depth: depthOf(directory), isDirectory: true });
    }
    rows.set(path, { path, depth: depthOf(path), isDirectory: false });
  }
  return [...rows.values()].sort((left, right) => left.path.localeCompare(right.path));
}

function commitsOf(text: string): readonly CommitLine[] {
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .flatMap((line) => {
      const [sha, subject, author, at] = line.split(UNIT_SEPARATOR);
      return sha === undefined || subject === undefined || author === undefined || at === undefined
        ? []
        : [{ sha, subject: redacted(subject), author: redacted(author), at }];
    });
}

async function openFile(root: string, revision: string, path: string): Promise<readonly string[]> {
  const text = await boundedProcess({ op: "git.show", root, revision, path });
  return redacted(text).split("\n").slice(0, LINE_CAP);
}

export async function readAuthoredFiles(requested: string | null): Promise<AuthoredFiles> {
  const root = filesRoot();
  const revision = (await boundedProcess({ op: "git.revision", root })).trim();
  const listing = await boundedProcess({ op: "git.tree", root, revision });
  const files = listing
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  // the opened path must be a member of the listing; nothing else is openable
  const openPath = requested !== null && files.includes(requested) ? requested : (files[0] ?? null);
  const openLines = openPath === null ? [] : await openFile(root, revision, openPath);
  const commits =
    openPath === null
      ? []
      : commitsOf(await boundedProcess({ op: "git.pathLog", root, path: openPath }));

  const shown = files.slice(0, TREE_CAP);
  return {
    root,
    revision,
    entries: treeOf(shown),
    // the tree is capped for the browser, so the cap is a stated fact rather
    // than a silently shorter list that reads as the whole repository
    sourceTotal: files.length,
    shownTotal: shown.length,
    truncated: files.length > shown.length,
    openPath,
    openLines,
    commits,
  };
}
