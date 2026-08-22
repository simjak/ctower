/**
 * The cockpit's measured geometry, taken off `board/design-refs-r2988-conductor`
 * at 1:1 (director ruling 2026-08-22 13:25Z).
 *
 * Both references are 2× captures, so every figure here is CSS pixels. The rule
 * the reference actually follows is: **the rail is fixed, the right pane is
 * anchored, and the centre takes the remainder.** The rail measured 243 and 254
 * across a 416px change in window width; the right pane measured 316 at the
 * width closest to ctower's content box.
 *
 * The rail is no longer one of these panes. It is the shell's single 248 rail
 * (D2, reversed 2026-08-22), so the cockpit's own box is centre + right at
 * exactly 1200 — which puts the centre at 884 and the whole surface at 1448,
 * inside the 1308–1724 the two references were captured at.
 */
export const WORKSPACE = "w-[316px]";

/**
 * Below this the three panes do not fit and the cockpit says so instead of
 * drawing them. 1024 − 248 rail − 48 gutters − 2 rules − 316 right leaves a
 * 410px centre, which is the first width where the breadcrumb and the composer
 * are both real. At 768 the same arithmetic leaves 154, and at 375 it leaves 0.
 */
export const PANES = "hidden lg:flex";
export const NARROW = "lg:hidden";

/**
 * The centre's breadcrumb row. The reference separates a 52px breadcrumb from a
 * 40px tab strip; ctower has no workspace tabs to draw, so only the breadcrumb
 * survives at its measured height.
 */
export const BREADCRUMB = "flex h-13 shrink-0 items-center gap-3 border-b border-line px-4";

/**
 * The right pane's tab row, and the bottom split's. The reference measured 35
 * and ~32; both round to the same row here because both carry one line of
 * 12.5px text with a pill.
 *
 * These deliberately do NOT match `BREADCRUMB`. The reference's centre rule
 * lands at 92 and its right-pane rule at 128 — there is no single horizon
 * across the panes, and the earlier build invented one.
 */
export const TAB_ROW = "flex h-9 shrink-0 items-center gap-1 border-b border-line px-2";

/** The bottom split's row measured ~32 in both references, four short of the top's. */
export const FOOT_TAB_ROW = "h-8 border-t";

/**
 * A row in the rail or the work list: a 32px fill, inset 4 each side, radius 4.
 *
 * The 4px of vertical pitch that makes a rail child row 40 is NOT here. The
 * reference's rail children are on a 40 pitch and its right-pane rows are on a
 * 32 pitch with no gap at all, so the gap belongs to the rail's call site.
 */
export const LIST_ROW = "mx-1 flex h-8 items-center rounded-sm px-2";
