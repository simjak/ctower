import type { ReactElement } from "react";
import { BoardScreen } from "./BoardScreen";
import type { BoardShape } from "./BoardScreen";
import { Frame } from "./Frame";

/**
 * The two boards T-028 puts on the bench, each on its own address so it can be
 * screenshotted alone: `gallery.html?screen=board` and `…=board-reference`.
 * Nothing is wired; both draw fixtures.
 */
export function screenFromSearch(search: string): BoardShape {
  return new URLSearchParams(search).get("screen") === "board-reference" ? "reference" : "recorded";
}

export function Screen({ shape }: { readonly shape: BoardShape }): ReactElement {
  return (
    <Frame>
      <BoardScreen shape={shape} />
    </Frame>
  );
}
