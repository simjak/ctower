/**
 * The cockpit's measured geometry, taken off `board/design-refs-r2988-conductor`
 * at 1:1 (operator ruling 2026-08-22 13:25Z).
 *
 * Both references are 2× captures, so every figure here is CSS pixels. The rail
 * measured 243 and 254 across a 416px change in window width, so it is fixed;
 * the right pane measured 316 at the width closest to ctower's 1200 content
 * box, so that is the anchor and the centre takes the remainder.
 *
 * The crew rail is 208 rather than the reference's 248 by the commander's
 * ruling: ctower keeps its own shell rail, so the cockpit's rail is a second
 * one and gives up width to let the workspace breathe.
 */
export const CREW_RAIL = "w-[208px]";
export const WORKSPACE = "w-[316px]";

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

/** A row in the rail or the work list: 40px pitch, 32px fill, inset 4. */
export const LIST_ROW = "mx-1 flex h-8 items-center rounded-sm px-2";
