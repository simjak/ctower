import type { ReactElement } from "react";
import type { BoardLane } from "@/read/interface";

/**
 * The six state marks `ctowerctl` prints, drawn in CSS and carrying the glyph
 * character as their text label. The mark is always derived from a recorded
 * fact; there is no "probably done" mark.
 */
export type GlyphName = "done" | "open" | "flight" | "held" | "parked" | "attn";

const CHARACTERS: Readonly<Record<GlyphName, string>> = {
  done: "●",
  open: "○",
  flight: "⟳",
  held: "⛔",
  parked: "⏸",
  attn: "⚠",
};

export function StateGlyph({ name }: { readonly name: GlyphName }): ReactElement {
  return <span className={`g g-${name}`}>{CHARACTERS[name]}</span>;
}

export function laneGlyph(lane: BoardLane, blocked: boolean): GlyphName {
  if (blocked) {
    return "held";
  }
  switch (lane) {
    case "complete":
      return "done";
    case "blocked":
      return "held";
    case "in_progress":
    case "in_review":
      return "flight";
    case "backlog":
    case "ready":
      return "open";
  }
}
