// Drivers for the read-layer decisions round-3 QA found wrong on the live board.
//
// Four screens each showed a number or a verdict that was not what the sources
// held: Explorer measured every branch against a 25-commit-stale local ref
// (#236), Org filed a quarter of the fleet under "project not recorded" while
// tmux held their project (#237), Heartbeats rendered a beat firing every ten
// minutes as never-fired and counted it in no tile (#238), and the Feed's chat
// view rendered the terminal's own wrap column and every spinner tick as a
// bubble (#242).
//
// Each of those decisions is a pure function on values, so this drives the real
// functions with the values the live sources produce — no bundler, no network,
// no live state, no clock, and no child process spawned. Nothing here runs a
// command or reads a file; it only asks what the surface would conclude.

import { chooseBase } from "../../apps/ctower-ui/src/read/sources/worktrees.ts";
import type { BaseProbe } from "../../apps/ctower-ui/src/read/sources/worktrees.ts";
import { projectOf } from "../../apps/ctower-ui/src/read/sources/crewRoster.ts";
import { markerCandidates } from "../../apps/ctower-ui/src/read/sources/cadenceCron.ts";
import { healthOf, registryOf } from "../../apps/ctower-ui/src/read/sources/cadenceHealth.ts";
import { rejoined, turnsOf, unindent } from "../../apps/ctower-ui/src/read/sources/tmuxBridge.ts";
import { noneOf, unreadOf, valueOf } from "../../apps/ctower-ui/src/read/sources/maybe.ts";
import type { Beat } from "../../apps/ctower-ui/src/read/interface.ts";

const results: Record<string, unknown> = {};

/* ── #236 · the diff base ─────────────────────────────────────────────────
   The defect verbatim: `origin/main` resolved, `main` resolved, and the surface
   picked `main` — which on that checkout was 25 commits behind, turning a
   six-file branch into 267 files changed. */

const probe = (ref: string, tracksRemote: boolean, head: string | null): BaseProbe => ({
  ref,
  tracksRemote,
  head: head === null ? unreadOf(`${ref} names no commit in this checkout`) : valueOf(head),
});

results.baseChoosesTheRemoteTrunk = chooseBase([
  probe("origin/main", true, "3a5e87ce"),
  probe("main", false, "423212c1"),
]);

// order must not decide it: a local ref listed first still loses to the remote
results.baseIgnoresProbeOrder = chooseBase([
  probe("main", false, "423212c1"),
  probe("origin/main", true, "3a5e87ce"),
]);

// a checkout with no remote still has a trunk, and the surface says which
results.baseFallsBackToLocalAndSaysSo = chooseBase([
  probe("origin/main", true, null),
  probe("main", false, "423212c1"),
]);

results.baseWithNothingResolvedIsUnread = chooseBase([
  probe("origin/main", true, null),
  probe("main", false, null),
]);

results.baseWithNoProbesIsUnread = chooseBase([]);

/* ── #237 · which project a crew is on ────────────────────────────────────
   `mc-designer-crew-profiles` had zero lines in the crew log and `@project`
   `ctower` on its live session. The roster read only the log. */

const logRead = { read: true, text: "" } as const;
const logMissing = { read: false, missing: true, reason: "no crew log exists at /x" } as const;
const logUnread = {
  read: false,
  missing: false,
  reason: "the crew log could not be read",
} as const;

results.projectFromTheSessionTagWhenTheLogIsSilent = projectOf(null, "ctower", logRead);
results.projectFromTheLogWhenItRecordedOne = projectOf("manibo", "ctower", logRead);
results.projectNotRecordedWhenNeitherHasOne = projectOf(null, null, logRead);
results.projectNotRecordedForAnEmptyTag = projectOf(null, "   ", logRead);
// an unreadable log plus a tag is still a known project: the tag answered
results.projectFromTheTagWhenTheLogIsUnreadable = projectOf(null, "bh-loop", logUnread);
// and with neither, an unreadable log stays unread rather than becoming "none"
results.projectStaysUnreadWhenNothingAnswered = projectOf(null, null, logUnread);
results.projectNotRecordedWhenThereIsNoLogFile = projectOf(null, null, logMissing);

/* ── #238 · a beat's fire marker, and the tiles ───────────────────────────
   `ctower-feed-notify` writes `state/ctower-feed-cursor.json` on every run and
   none of the three guessed filenames, so its row could go neither green nor
   red — and the four tiles counted four of five registered beats. */

results.registeredBeatCarriesItsOwnMarker = markerCandidates("ctower-feed-notify").map((path) =>
  path.slice(path.indexOf("/state/"))
);
results.unregisteredBeatFallsBackToTheConvention = markerCandidates("idle-alarm").map((path) =>
  path.slice(path.indexOf("/state/"))
);

const beat = (name: string, health: Beat["health"]): Beat => ({
  seat: "agent",
  beat: name,
  schedule: "*/10 * * * *",
  lastFire: null,
  nextFire: null,
  health,
  why: null,
});

results.tilesCountEveryRegisteredBeat = registryOf(
  [
    beat("a", "alive"),
    beat("b", "alive"),
    beat("c", "late"),
    beat("d", "dead"),
    beat("e", "unknown"),
  ],
  "crontab -l",
  "2026-08-04T08:00:00.000Z",
  "rule"
);

// the exact live shape QA found: five registered, four resolvable
results.tilesOnTheObservedRegistry = registryOf(
  [
    beat("ctower-migration-drive", "alive"),
    beat("ctower-beat-watchdog", "alive"),
    beat("idle-alarm", "alive"),
    beat("wip-alarm", "alive"),
    beat("ctower-feed-notify", "unknown"),
  ],
  "crontab -l",
  "2026-08-04T08:00:00.000Z",
  "rule"
);

// a beat whose fire is known but whose schedule states no interval is not the
// same claim as a beat that never fired
results.healthWithNoLastFire = healthOf(null, 600_000, 1_000_000_000);
results.healthWithNoInterval = healthOf(999_000_000, null, 1_000_000_000);
results.healthOfAFireOneIntervalOld = healthOf(1_000_000_000 - 600_000, 600_000, 1_000_000_000);

/* ── #242 · the chat view's turns ─────────────────────────────────────────
   The capture arrives with the TUI's two-column padding, and five of eleven
   bubbles on one screenful were spinner ticks and scheduled-wake lines. */

// the first two lines are one paragraph the session wrapped at column 120, kept
// verbatim from the QA evidence in #242 including the hanging continuation
const CAPTURE = [
  "  ● manibo found the root cause of the conflict waves I'd logged three separate times. A generated file — the test",
  "  inventory under docs — is tracked in git and regenerated by every PR that adds a test.",
  "",
  "  ✻ Churned for 52s",
  "  ✻ Running scheduled task (Aug 3 8:58am)",
  "  ● Two staging tenant-worker pods are Terminating.",
  "    ⎿ Ran 1 shell command",
  "      pods listed",
  "  ✻ Churned for 33s",
];

const turns = turnsOf(CAPTURE, 120);
results.chatTurns = turns.map((turn) => ({
  body: turn.body,
  notes: turn.notes,
  tools: turn.tools.map((tool) => tool.summary),
}));
results.chatTurnCount = turns.length;
results.chatStatusLineCount = turns.reduce((total, turn) => total + turn.notes.length, 0);

// a status line before any turn has opened still cannot become a bubble
results.chatLeadingStatus = turnsOf(["  ✻ Churned for 4s", "  ● a real turn"], 120).map((turn) => ({
  body: turn.body,
  notes: turn.notes,
}));

results.unindentStripsOnlyTheSharedPadding = unindent([
  "  a line",
  "      an indented quote",
  "  another line",
]);
results.unindentLeavesAnUnpaddedBodyAlone = unindent(["a line", "  a quote"]);

// the reconstruction rule, exercised on its own: a line that reached the wrap
// column continues; a line that stopped well short of it ended its paragraph
results.rejoinsAWrappedLine = rejoined(
  ["a line that ran all the way out to the pane's own wrap column and kept going", "onto the next"],
  80
);
results.leavesAShortLineAlone = rejoined(["a short line.", "a new paragraph."], 80);
results.rejoinsNothingWithoutAWidth = rejoined(
  ["a line that ran all the way out to the pane's own wrap column and kept going", "onto the next"],
  null
);
results.rejoinKeepsABlankLineAsABreak = rejoined(
  ["a line that ran all the way out to the pane's own wrap column and kept going", "", "after"],
  80
);

// `noneOf` is exercised so the driver fails loudly if the Known constructors
// ever stop being importable from this module
results.knownNone = noneOf("nothing recorded");

process.stdout.write(JSON.stringify(results, null, 2));
