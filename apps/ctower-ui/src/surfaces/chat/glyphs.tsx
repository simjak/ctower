import type { ReactElement } from "react";

/**
 * The chat workspace's icon set.
 *
 * The de-texting amendment moves meaning out of prose and into elements, which
 * only works if the elements are legible on their own. Each of these is drawn
 * at 14–16px from the same 1.4px stroke as the frame's own mark, carries
 * `aria-hidden`, and is always paired with either a visible label or a `title`
 * on its control — an icon whose only meaning is in a hover is a meaning a
 * touch screen does not have.
 */

const STROKE = { stroke: "currentColor", strokeWidth: 1.4, strokeLinecap: "round" } as const;

export function PlusGlyph(): ReactElement {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M8 3v10M3 8h10" {...STROKE} />
    </svg>
  );
}

export function SendGlyph(): ReactElement {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M8 13V3.5M4 7.2 8 3.2l4 4" {...STROKE} strokeLinejoin="round" />
    </svg>
  );
}

export function TicketGlyph(): ReactElement {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <rect x="2.2" y="3.7" width="11.6" height="8.6" rx="1.6" {...STROKE} />
      <path d="M2.2 7.2h11.6" {...STROKE} />
    </svg>
  );
}

export function ChangeGlyph(): ReactElement {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden>
      <circle cx="4.4" cy="4" r="1.7" {...STROKE} />
      <circle cx="4.4" cy="12" r="1.7" {...STROKE} />
      <circle cx="11.6" cy="8" r="1.7" {...STROKE} />
      <path d="M4.4 5.7v4.6M6.1 4h2.4a1.5 1.5 0 0 1 1.5 1.5v.9" {...STROKE} />
    </svg>
  );
}

export function LinkThreadGlyph(): ReactElement {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path d="M6.6 9.4a2.6 2.6 0 0 0 3.7 0l2-2a2.6 2.6 0 1 0-3.7-3.7l-.9.9" {...STROKE} />
      <path d="M9.4 6.6a2.6 2.6 0 0 0-3.7 0l-2 2a2.6 2.6 0 1 0 3.7 3.7l.9-.9" {...STROKE} />
    </svg>
  );
}

/** The empty-pane mark: an outline, so nothing reads as a state that is set. */
export function NothingGlyph(): ReactElement {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden>
      <rect x="3.5" y="5.5" width="19" height="15" rx="2.4" {...STROKE} />
      <path d="M3.5 10.5h19M9.6 20.5v-10" {...STROKE} />
    </svg>
  );
}
