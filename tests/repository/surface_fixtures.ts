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
import { healthOf, registryOf } from "../../apps/ctower-ui/src/read/sources/cadenceHealth.ts";
import { scheduleIntervalMs } from "../../apps/ctower-ui/src/read/beatRegistry.ts";
import { rejoined, turnsOf, unindent } from "../../apps/ctower-ui/src/read/sources/tmuxBridge.ts";
import { noneOf, unreadOf, valueOf } from "../../apps/ctower-ui/src/read/sources/maybe.ts";
import { reclassified } from "../../apps/ctower-ui/src/read/bounded.ts";
import {
  boardCardContextFor,
  boardEmptyKind,
} from "../../apps/ctower-ui/src/read/boardProjection.ts";
import type { Beat, BoardCard } from "../../apps/ctower-ui/src/read/interface.ts";

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

/* ── #238 · how long silence is allowed to last, and the tiles ────────────
   The registry is the record's now, so lateness is decided by the routine's own
   minute/hour set rather than by a guessed marker file. A set is not necessarily
   evenly spaced: `0,5 * * * *` fires twice an hour with gaps of five minutes and
   fifty-five, and calling the interval five would mark that beat late for most
   of every hour it was never scheduled to fire in. */

const schedule = (minutes: readonly number[], hours: readonly number[] | null) => ({
  routineRef: "ctower.beat.fixture@1",
  beatKey: "fixture",
  targetSession: "commander",
  nextFireAt: "2026-08-14T23:09:00Z",
  minutes,
  hours,
  timezone: "UTC",
});

results.evenScheduleIntervalIsItsGap = scheduleIntervalMs(schedule([9, 24, 39, 54], null));
results.unevenScheduleTakesTheWidestGap = scheduleIntervalMs(schedule([0, 5], null));
results.dailyScheduleIsADay = scheduleIntervalMs(schedule([12], [7]));
results.wrapAroundGapIsCounted = scheduleIntervalMs(schedule([0], [0, 1]));

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
  "/v1/runtime/beat-routines",
  "2026-08-04T08:00:00.000Z",
  "rule"
);

// the exact live shape QA found: five registered, four with a dispatch on record
results.tilesOnTheObservedRegistry = registryOf(
  [
    beat("ctower-migration-drive", "alive"),
    beat("ctower-beat-watchdog", "alive"),
    beat("idle-alarm", "alive"),
    beat("wip-alarm", "alive"),
    beat("ctower-feed-notify", "unknown"),
  ],
  "/v1/runtime/beat-routines",
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

/* ── the status a refusal carries ─────────────────────────────────────────
   The board tells "not allowed to look" from "could not reach" by the status on
   the typed failure. The retry loop folds an already-built failure back into a
   classification, and that fold used to drop the status — so a 401 reached the
   screen as a generic unreachable-source block. */

results.refusalKeepsItsStatus = reclassified({
  reason: "the read API answered 401",
  failureClass: "permanent",
  attempts: 1,
  elapsedMs: 13,
  status: 401,
});
results.failureWithNoStatusStaysWithout = reclassified({
  reason: "the read attempt timed out",
  failureClass: "transient",
  attempts: 2,
  elapsedMs: 4000,
  status: null,
});

/* ── the 0-of-0 board decision (two empties, neither blank) ────────────────
   A scoped board that answers watermark 0 of 0 with zero cards is never
   rendered as a normal empty board — an empty answer rendered as truth is the
   honesty defect this surface guards, one level deeper (during the runtime
   swap on 2026-08-04 the board said "0 of 0" while cards sat safe at a higher
   watermark). There are TWO ways a board answers 0 of 0, told apart by the
   portfolio's watermark in the same render:

   * portfolio ALSO 0 (or the portfolio read did not answer) -> restart-fresh:
     the API is restarting/rebuilding or the instance is genuinely fresh; this
     is the refusal block.
   * portfolio > 0 -> true-empty-project: the instance holds records, so THIS
     project's import chain has not run; it renders its own named block with a
     link to the portfolio view.

   Anything else — any watermark > 0 (a genuinely empty PROJECT under a nonzero
   watermark included) and any board that actually has cards — is normal and
   must NOT change. */

const boardProbe = (
  projectionWatermark: number,
  cardCount: number,
  portfolioWatermark: number | null
): string =>
  boardEmptyKind({
    projectionWatermark,
    entries: Array.from({ length: cardCount }),
    portfolioWatermark,
  });

results.zeroOfZeroPortfolioZeroIsRestartFresh = boardProbe(0, 0, 0);
results.zeroOfZeroPortfolioNonzeroIsTrueEmptyProject = boardProbe(0, 0, 462);
results.zeroOfZeroPortfolioUnreachableIsRestartFresh = boardProbe(0, 0, null);
results.nonzeroWatermarkEmptyProjectRendersNormally = boardProbe(462, 0, 462);
results.zeroWatermarkWithCardsRendersNormally = boardProbe(0, 3, 462);
results.nonzeroWatermarkWithCardsRendersNormally = boardProbe(462, 279, 462);

/* ── #337 · every Board-card context member is rendered from its own fact ──
   The API response carries all five members. The surface used only tenant
   identity (and only in the portfolio fallback), substituted delivery facts
   for change references, and discarded labels, human-waiting, and delivery
   availability entirely. Drive the exact QA fixture through the pure display
   projection so component markup cannot need to reinterpret discriminants. */

const contextCard = {
  tenantDisplayIdentity: { state: "known", displayName: "Ctower" },
  changeReferences: [
    {
      repository: "simjak/ctower",
      change_identity: "326",
      reference: "https://github.com/simjak/ctower/pull/326",
      recorded_at: "2026-08-06T12:00:00Z",
    },
  ],
  appliedLabels: [
    {
      label_key: "visual-gate",
      label: "Visual gate",
      vocabulary_revision: 1,
      applied_at: "2026-08-06T12:01:00Z",
    },
  ],
  humanWaiting: {
    state: "waiting",
    finding_id: "01989d83-bf65-7db0-8598-9a4407bde5b5",
    kind_key: "needs_visual_qa",
    reason_code: "vision_path_deferred",
  },
  deliverySurfaceAvailability: { state: "no_qualifying_checkpoint" },
} as unknown as BoardCard;

results.boardCardContextSet = boardCardContextFor(contextCard);
results.boardCardExplicitEmptyContextSet = boardCardContextFor({
  tenantDisplayIdentity: { state: "unknown", missingSource: "tenant.display_name" },
  changeReferences: [],
  appliedLabels: [],
  humanWaiting: { state: "not_waiting" },
  deliverySurfaceAvailability: { state: "no_qualifying_checkpoint" },
} as unknown as BoardCard);

// `noneOf` is exercised so the driver fails loudly if the Known constructors
// ever stop being importable from this module
results.knownNone = noneOf("nothing recorded");

process.stdout.write(JSON.stringify(results, null, 2));
