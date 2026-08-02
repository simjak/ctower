"use client";

import { useRouter } from "next/navigation";
import { useCallback } from "react";
import type { ReactElement } from "react";
import type { TreeEntry } from "@/read/interface";

/**
 * The tree really opens files. The selection lives in the URL, so the pane, the
 * path line and the commit list beside it are all rendered on the server from
 * the same choice.
 */
export function FileTree({
  entries,
  openPath,
  route,
}: {
  readonly entries: readonly TreeEntry[];
  readonly openPath: string | null;
  readonly route: string;
}): ReactElement {
  const router = useRouter();
  const openFile = useCallback(
    (path: string): void => {
      router.push(`${route}?path=${encodeURIComponent(path)}`);
    },
    [route, router]
  );

  return (
    <div className="tree">
      {entries.map((entry) => {
        const name = entry.path.split("/").at(-1) ?? entry.path;
        const indent = { paddingLeft: `${(entry.depth * 14 + 8).toString()}px` };
        if (entry.isDirectory) {
          return (
            <div className="dir" style={indent} key={entry.path}>
              <span className="cw">⌄</span>
              {name}/
            </div>
          );
        }
        return (
          <label
            style={{ ...indent, paddingLeft: `${(entry.depth * 14 + 24).toString()}px` }}
            key={entry.path}
          >
            <input
              type="radio"
              name="file"
              value={entry.path}
              checked={entry.path === openPath}
              onChange={() => {
                openFile(entry.path);
              }}
            />
            {name}
          </label>
        );
      })}
    </div>
  );
}
