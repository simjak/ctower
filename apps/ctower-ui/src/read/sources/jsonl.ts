import { readFile } from "node:fs/promises";

/**
 * Reading an append-only JSONL file that another repository is writing right
 * now.
 *
 * `state/inbox.jsonl` belongs to Mission Control and is appended to while this
 * surface reads it. A read can therefore land mid-write and see a final line
 * with no newline yet, or with only half a JSON object. Two things must not
 * happen: the screen must not crash, and it must not quietly show one message
 * fewer than the file holds and call that the inbox.
 *
 * So the tail is treated as a first-class outcome. A trailing fragment is
 * skipped and *counted*, and the screen states the count — "3 lines at the tail
 * were mid-write" is a true sentence; silently dropping them is not.
 *
 * Nothing here writes, locks, truncates or renames. The file is opened read-only
 * and closed.
 */

export interface JsonlScan<T> {
  readonly records: readonly T[];
  /** Complete lines whose JSON did not parse or did not match the shape. */
  readonly malformed: number;
  /** A final line with no terminating newline: an append caught mid-write. */
  readonly partialTail: boolean;
  readonly totalLines: number;
}

/**
 * Parse a JSONL buffer. `shape` returns the typed record or `null` to reject a
 * line; a rejection is counted, never guessed at.
 */
export function scanJsonl<T>(text: string, shape: (value: unknown) => T | null): JsonlScan<T> {
  const endsClean = text.length === 0 || text.endsWith("\n");
  const lines = text.split("\n");
  const trailing = lines.at(-1) ?? "";
  // split leaves an empty final element for a clean file; a non-empty one is a
  // line the writer had not finished when this read happened.
  const partialTail = !endsClean && trailing.trim().length > 0;
  const complete = partialTail ? lines.slice(0, -1) : lines;

  const records: T[] = [];
  let malformed = 0;
  let totalLines = 0;
  for (const line of complete) {
    if (line.trim().length === 0) {
      continue;
    }
    totalLines += 1;
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      malformed += 1;
      continue;
    }
    const record = shape(parsed);
    if (record === null) {
      malformed += 1;
      continue;
    }
    records.push(record);
  }
  return { records, malformed, partialTail, totalLines };
}

/** Read a JSONL file from disk and scan it. Read-only; never writes or locks. */
export async function readJsonl<T>(
  path: string,
  shape: (value: unknown) => T | null
): Promise<JsonlScan<T>> {
  return scanJsonl(await readFile(path, "utf8"), shape);
}
