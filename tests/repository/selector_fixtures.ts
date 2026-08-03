// Deterministic mixed present/unavailable drivers for the ranking selectors.
//
// Round-2 review of PR #207 found both selectors discarding unavailable inputs
// before ranking, so a failed candidate could silently lose to a survivor that
// was not actually the most recent. These cases pin every branch of that
// behaviour, including the mixed ones the live all-sources-down probe could not
// reach.
//
// The selector module is pure and imports only a type, so Node runs it directly
// with type stripping — no bundler, no network, no live state, no clock.

import { rankCandidates, rankStrictly } from "../../apps/ctower-ui/src/read/selectors.ts";
import type { Candidate } from "../../apps/ctower-ui/src/read/selectors.ts";

const SOURCE = { lands: "#186", what: "any candidate" };

function present(value: string, orderBy: string): Candidate<string> {
  return { reading: { state: "present", value }, orderBy };
}

function unavailable(reason: string): Candidate<string> {
  return {
    reading: {
      state: "unavailable",
      failure: { reason, failureClass: "transient", attempts: 3, elapsedMs: 120 },
    },
    orderBy: "",
  };
}

function absent(): Candidate<string> {
  return { reading: { state: "absent", source: SOURCE }, orderBy: "" };
}

const results: Record<string, unknown> = {};

// 1 — a complete fan-out ranks, and says nothing was unread.
results.complete = rankCandidates(
  [present("older", "2026-08-01T00:00:00Z"), present("newer", "2026-08-02T00:00:00Z")],
  SOURCE
);

// 2 — THE ROUND-2 DEFECT: one candidate answers, one does not. The failure must
//     survive into the result; the winner is provisional, not confident.
results.mixed = rankCandidates(
  [present("survivor", "2026-08-01T00:00:00Z"), unavailable("audit read timed out")],
  SOURCE
);

// 3 — the unread candidate is ordered first in the input, proving the count is
//     not an artefact of position.
results.mixedFirst = rankCandidates(
  [unavailable("audit read timed out"), present("survivor", "2026-08-01T00:00:00Z")],
  SOURCE
);

// 4 — several unread candidates are all counted, not just the first.
results.mixedMany = rankCandidates(
  [
    present("survivor", "2026-08-01T00:00:00Z"),
    unavailable("first failure"),
    unavailable("second failure"),
  ],
  SOURCE
);

// 5 — every candidate unavailable stays unavailable, never absent.
results.allUnavailable = rankCandidates(
  [unavailable("first failure"), unavailable("second failure")],
  SOURCE
);

// 6 — genuinely nothing recorded is absent, not unavailable.
results.allAbsent = rankCandidates([absent(), absent()], SOURCE);

// 7 — an empty fan-out is absent.
results.empty = rankCandidates([], SOURCE);

// 8 — absent candidates alongside a present one do not count as unread: an
//     empty stream answered, it just had nothing in it.
results.absentDoesNotCountAsUnread = rankCandidates(
  [present("survivor", "2026-08-01T00:00:00Z"), absent()],
  SOURCE
);

// 9 — STRICT: a superlative with nowhere to carry a caveat refuses on any gap.
results.strictMixed = rankStrictly(
  [present("survivor", "2026-08-01T00:00:00Z"), unavailable("join read failed")],
  SOURCE
);

// 10 — STRICT still answers when the fan-out is complete.
results.strictComplete = rankStrictly(
  [present("older", "2026-08-01T00:00:00Z"), present("newer", "2026-08-02T00:00:00Z")],
  SOURCE
);

// 11 — THE ROUND-2 FALLBACK: every join failed. The old code fell back to the
//      first card and returned `present`; this must refuse.
results.strictAllUnavailable = rankStrictly(
  [unavailable("join one failed"), unavailable("join two failed")],
  SOURCE
);

process.stdout.write(JSON.stringify(results, null, 2));
