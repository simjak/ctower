// Driver for gh#318 — the Inbox severity chip rendered the record's own word
// for its info tier, "info", which the operator's no-generic-status-labels
// rule bans case-insensitively (never INFO/WARNING/ERROR/LIVE). This drives
// the real `severityLabel` chokepoint with the values Mission Control's
// `tools/notify` actually sends (P0, P1, info) and with adversarial values
// outside that vocabulary, so the guard is checked as a class rather than as
// the one instance QA found.

import { severityLabel } from "../../apps/ctower-ui/src/surfaces/severity.ts";

const results: Record<string, unknown> = {};

const BANNED_GENERIC_LABEL = /^(?:info|warning|error|live)$/i;

function attempt(severity: string): { readonly thrown: boolean; readonly label: string | null } {
  try {
    return { thrown: false, label: severityLabel(severity) };
  } catch {
    return { thrown: true, label: null };
  }
}

// the record's real vocabulary — the only three values `tools/notify` sends
results.realInfo = attempt("info");
results.realP0 = attempt("P0");
results.realP1 = attempt("P1");

// adversarial values outside that vocabulary, exercising every banned word in
// every case a rendered chip could carry it
const adversarial = ["INFO", "Info", "WARNING", "warning", "ERROR", "error", "LIVE", "Live"];
for (const severity of adversarial) {
  results[`adversarial_${severity}`] = attempt(severity);
}

// the class guard itself: across the record's real vocabulary and every
// adversarial value above, no resolved label may ever match the banned set —
// a value this surface has not vetted must fail loud instead
const domain = ["info", "P0", "P1", ...adversarial];
results.neverResolvesToABannedLabel = domain.every((severity) => {
  try {
    return !BANNED_GENERIC_LABEL.test(severityLabel(severity));
  } catch {
    // thrown means it never reached a render as the banned word either
    return true;
  }
});

process.stdout.write(JSON.stringify(results, null, 2));
