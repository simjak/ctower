"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import type { ReactElement } from "react";

export interface TreeRow {
  readonly path: string;
  readonly depth: number;
  readonly isDirectory: boolean;
  /** A short status mark, e.g. `+41`; omitted when there is none. */
  readonly badge?: string;
  readonly badgeTone?: "changed" | "added";
}

/**
 * The shared file tree, collapsed by default.
 *
 * The design audit found both file surfaces rendering every path as one flat
 * eleven-thousand-pixel column at nine-point type — a data dump, not a tool.
 * So directories start closed, expansion is one click and lives in the URL (so
 * the server renders the same tree the reader sees), and the type floor is
 * 12px, because a tree you cannot read is not a tree.
 */
export function TreePane({
  rows,
  openPath,
  expanded,
  route,
  keepParams = {},
}: {
  readonly rows: readonly TreeRow[];
  readonly openPath: string | null;
  readonly expanded: readonly string[];
  readonly route: string;
  readonly keepParams?: Readonly<Record<string, string>>;
}): ReactElement {
  const router = useRouter();

  const go = useCallback(
    (next: Readonly<Record<string, string>>): void => {
      const params = new URLSearchParams({ ...keepParams, ...next });
      router.push(`${route}?${params.toString()}`);
    },
    [keepParams, route, router]
  );

  const isOpen = (path: string): boolean => expanded.includes(path);
  const parentOf = (path: string): string => path.split("/").slice(0, -1).join("/");
  const visible = rows.filter((row) => {
    const parent = parentOf(row.path);
    if (parent === "") {
      return true;
    }
    return parent
      .split("/")
      .map((_, index, parts) => parts.slice(0, index + 1).join("/"))
      .every(isOpen);
  });

  const toggle = (path: string): void => {
    const next = isOpen(path)
      ? expanded.filter((entry) => entry !== path && !entry.startsWith(`${path}/`))
      : [...expanded, path];
    go({ open: next.join(",") });
  };

  return (
    <div className="tree" style={{ fontSize: "12px" }}>
      {visible.map((row) => {
        const name = row.path.split("/").at(-1) ?? row.path;
        if (row.isDirectory) {
          return (
            <button
              className="dir"
              type="button"
              key={row.path}
              onClick={() => {
                toggle(row.path);
              }}
              aria-expanded={isOpen(row.path)}
              style={{
                paddingLeft: `${(row.depth * 12 + 8).toString()}px`,
                fontSize: "12px",
                background: "none",
                border: 0,
                width: "100%",
                textAlign: "left",
                cursor: "pointer",
                font: "inherit",
              }}
            >
              <span className="cw">{isOpen(row.path) ? "⌄" : "›"}</span>
              {name}/
            </button>
          );
        }
        return (
          <label
            key={row.path}
            style={{ paddingLeft: `${(row.depth * 12 + 22).toString()}px`, fontSize: "12px" }}
          >
            <input
              type="radio"
              name="treefile"
              value={row.path}
              checked={row.path === openPath}
              onChange={() => {
                go({ path: row.path, open: expanded.join(",") });
              }}
            />
            {name}
            {row.badge === undefined ? null : (
              <span className={row.badgeTone === "added" ? "fstat a" : "fstat m"}>{row.badge}</span>
            )}
          </label>
        );
      })}
      {visible.length === 0 ? <div className="leaf">nothing to show at this revision</div> : null}
    </div>
  );
}
