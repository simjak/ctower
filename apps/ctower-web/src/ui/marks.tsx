import type { ReactElement } from "react";
import { cn } from "./cn";

/**
 * The six marks, shared with the CLI.
 *
 * `DESIGN.md` makes this non-negotiable: these are the glyphs `ctowerctl`
 * prints, and they change in both places or neither, by an authored decision
 * rather than a UI restyle. That is why they are characters here and not icons
 * — an icon set cannot be kept honest against a terminal.
 *
 * There is deliberately no mark for `unknown`. A state with no recorded fact
 * draws nothing at all and says so in words, because borrowing a neighbour's
 * glyph is how a read that never answered gets rendered as a state that did.
 */
export type MarkName = "done" | "idle" | "working" | "dead" | "parked" | "warn";

const GLYPH: Readonly<Record<MarkName, string>> = {
  done: "●",
  idle: "○",
  working: "⟳",
  dead: "⛔",
  parked: "⏸",
  warn: "⚠",
};

const INK: Readonly<Record<MarkName, string>> = {
  done: "text-ok",
  idle: "text-muted",
  working: "text-amber",
  dead: "text-danger",
  parked: "text-muted",
  warn: "text-amber-strong",
};

/** The word each mark carries for a screen reader, and for the `title`. */
const WORD: Readonly<Record<MarkName, string>> = {
  done: "done",
  idle: "idle",
  working: "working",
  dead: "dead",
  parked: "parked",
  warn: "warning",
};

export function Mark({
  name,
  className,
}: {
  readonly name: MarkName;
  readonly className?: string;
}): ReactElement {
  return (
    // `relative` is load-bearing, not decoration. The screen-reader word is
    // `position: absolute`, and with no positioned ancestor it resolves against
    // the initial containing block — so a mark inside a scrolling pane lays its
    // hidden word out against the document instead, and every row past the fold
    // extends the page's own scroll box. Anchoring it to the mark keeps it
    // inside whatever clips the mark.
    <span className={cn("mono relative inline-block w-[1.4em] shrink-0", INK[name], className)}>
      <span aria-hidden>{GLYPH[name]}</span>
      <span className="sr-only">{WORD[name]}</span>
    </span>
  );
}
