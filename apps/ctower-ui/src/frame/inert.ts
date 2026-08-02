import type { CSSProperties } from "react";

/**
 * Read-only v1's inert affordances.
 *
 * A control this surface cannot honour has to *look* like it cannot be
 * honoured — a live-looking button that silently refuses is the dead control
 * the craft rules forbid. These are the only two treatments; every disabled
 * affordance on every screen uses them, so inertness reads the same way twice.
 */
export const INERT_CONTROL: CSSProperties = { opacity: 0.5, cursor: "not-allowed" };

export const INERT_FIELD: CSSProperties = {
  opacity: 0.6,
  cursor: "not-allowed",
  background: "var(--surface)",
};
