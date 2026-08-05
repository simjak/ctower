/**
 * Display vocabulary for an inbox message's severity.
 *
 * Mission Control's `tools/notify` sends exactly three severities: `P0`, `P1`
 * and `info` — and its own `--help` text calls an info-severity message "a
 * terse note", never "info". `info` is also the literal generic status word
 * the operator's no-generic-status-labels rule bans (never INFO/WARNING/
 * ERROR/LIVE), so it does not reach a screen unmapped: every severity resolves
 * through the table below, and one this surface has not vetted fails loud
 * instead of silently carrying a banned word onto the chip.
 */

const BANNED_GENERIC_LABEL = /^(?:info|warning|error|live)$/i;

const KNOWN_SEVERITY_LABELS: Readonly<Record<string, string>> = {
  info: "NOTE",
  P0: "P0",
  P1: "P1",
};

/** The word the chip renders. Never the record's own word for the info tier. */
export function severityLabel(severity: string): string {
  const label = KNOWN_SEVERITY_LABELS[severity] ?? severity;
  if (BANNED_GENERIC_LABEL.test(label)) {
    throw new Error(`severityLabel: "${severity}" resolves to a banned generic status label`);
  }
  return label;
}

/** The verdict-chip tier a severity renders in: paged (priority) or noted. */
export function severityClass(severity: string): string {
  return severity.toUpperCase().startsWith("P") ? "verdict v-changes" : "verdict v-filed";
}
