import { httpRecordAdapter } from "./httpRecordAdapter";
import { readCronCadence } from "./sources/cadenceCron";
import { readCrewProfile, readCrewRoster } from "./sources/crewRoster";
import { readDeliveryMetrics } from "./sources/delivery";
import { readSystemdCadence } from "./sources/cadenceSystemd";
import { readAuthoredFiles } from "./sources/gitTree";
import { cadenceSourceName } from "./sources/paths";
import { readPortfolio } from "./portfolio";
import { readSessionStream, readSessionWorkspace } from "./sources/tmuxBridge";
import { readSessionWorktree } from "./sources/worktrees";
import { reading } from "./outcome";
import type {
  AuthoredFiles,
  CadenceRegistry,
  CrewLookup,
  CrewRoster,
  CrewRow,
  SessionStream,
  RecordAdapter,
  Reading,
  SessionWorkspace,
  SessionWorktree,
} from "./interface";

/**
 * The swap seam.
 *
 * One source per screen, each named here and nowhere else. A screen asks the
 * adapter for its reading and never learns which source answered, so replacing
 * a source is an edit to this file alone — the component-C pattern applied to
 * reads. Board and Ticket read the instance's REST paths today and swap to a
 * typed feed here; the six wave-2 screens swap to their native sources the same
 * way.
 *
 * Read bindings go through `reading`, so a source that refuses or cannot be
 * reached arrives at its screen as a typed failure rather than as an empty
 * value. The Inbox send and promotion actions are deliberately separate: each
 * asks an existing server-authoritative mutation path and neither grants any
 * authority in the browser.
 */

export type ScreenKey =
  | "board"
  | "portfolio"
  | "ticket"
  | "inbox"
  | "heartbeats"
  | "files"
  | "workspace"
  | "explorer"
  | "feed"
  | "metrics"
  | "team"
  | "crew";

/** Which source answers each screen today, for the provenance foot. */
export const SOURCE_LABELS: Readonly<Record<ScreenKey, string>> = {
  board: "ctower read API · /v1/board",
  portfolio: "ctower read API · /v1/board per project + /v1/inbox/threads",
  ticket: "ctower read API · /v1/tickets/{id} + /audit",
  inbox:
    "ctower API · /v1/inbox/threads + /v1/inbox/threads/{id} + /v1/inbox/correspondents" +
    " + /v1/inbox/messages + /v1/inbox/notifications + /promotion",
  heartbeats:
    cadenceSourceName() === "systemd" ? "systemd user timers" : "host crontab + state markers",
  files: "git tree",
  workspace: "live tmux sessions + git",
  explorer: "git worktree list + diff",
  feed: "live tmux sessions · capture-pane",
  metrics: "git first-parent trunk history per project",
  team: "live tmux sessions + mission-control state/crew-log.jsonl + personas/",
  crew: "the team sources + mission-control coordination/*.status.md + state/escapes.jsonl + trunk history",
};

function cadenceSource(): () => Promise<CadenceRegistry> {
  return cadenceSourceName() === "systemd" ? readSystemdCadence : readCronCadence;
}

export const recordAdapter: RecordAdapter = {
  instance: httpRecordAdapter.instance,
  board: httpRecordAdapter.board,
  boardCards: httpRecordAdapter.boardCards,
  // the portfolio composes the reads above rather than adding a source: one
  // card-only board per configured project, plus the one inbox projection
  portfolio: readPortfolio,
  ticket: httpRecordAdapter.ticket,
  ticketAudit: httpRecordAdapter.ticketAudit,
  workSessions: httpRecordAdapter.workSessions,
  inbox: httpRecordAdapter.inbox,
  inboxThread: httpRecordAdapter.inboxThread,
  inboxCorrespondent: httpRecordAdapter.inboxCorrespondent,
  inboxCorrespondents: httpRecordAdapter.inboxCorrespondents,
  inboxPromotionPicker: httpRecordAdapter.inboxPromotionPicker,

  cadenceRegistry: async (): Promise<Reading<CadenceRegistry>> => await reading(cadenceSource()),
  authoredFiles: async (path: string | null): Promise<Reading<AuthoredFiles>> =>
    await reading(async () => await readAuthoredFiles(path)),
  sessionWorkspace: async (crew: string | null): Promise<Reading<SessionWorkspace>> =>
    await reading(async () => await readSessionWorkspace(crew)),
  sessionWorktree: async (
    worktree: string | null,
    path: string | null
  ): Promise<Reading<SessionWorktree>> =>
    await reading(async () => await readSessionWorktree(worktree, path)),
  sessionStream: async (subject: string | null): Promise<Reading<SessionStream>> =>
    await reading(async () => await readSessionStream(subject)),
  // the delivery source returns its own Reading: the fan-out across projects can
  // be partly unreadable, and that has to reach the screen, not be flattened
  deliveryMetrics: readDeliveryMetrics,
  crewRoster: async (project: string | null, seat: string | null): Promise<Reading<CrewRoster>> =>
    await reading(async () => await readCrewRoster(project, seat)),
  crewProfile: async (crew: string): Promise<Reading<CrewLookup>> =>
    await reading(async () => await readCrewProfile(crew)),
};

/**
 * The crew profile page's own terminal read.
 *
 * The pane's bytes are a second, independent read from the identity lookup
 * above: a lookup that did not find a live crew has no session name to ask
 * for, and a lookup that did is read again rather than reusing a value the
 * profile source did not carry. `Reading` is unwrapped here, inside the read
 * boundary, so no screen has to branch on `reading.state` to decide whether
 * it has a session name to read a pane for.
 */
export async function crewTerminalStream(
  lookup: Reading<CrewLookup>
): Promise<Reading<SessionStream>> {
  if (lookup.state !== "present" || lookup.value.found !== "crew") {
    return {
      state: "absent",
      source: { absence: "silence", what: "a pane for a crew this lookup did not find" },
    };
  }
  return await recordAdapter.sessionStream(lookup.value.profile.sessionName);
}

/**
 * The seat aggregate's own terminal reads: every crew this seat has live,
 * each with its own independently read pane, zipped together so a screen
 * never indexes two arrays by hand to line a crew back up with its stream.
 *
 * A roster read that did not land yet has no crews to read a pane for, so
 * this returns the empty list rather than inspecting `reading.state` a
 * second time outside the boundary that is allowed to.
 */
export async function seatTerminalStreams(
  roster: Reading<CrewRoster>,
  seatLabel: string
): Promise<readonly { readonly crew: CrewRow; readonly stream: Reading<SessionStream> }[]> {
  if (roster.state !== "present") {
    return [];
  }
  const crews = roster.value.groups
    .flatMap((group) => group.crews)
    .filter((row) => row.seatLabel.known === "value" && row.seatLabel.value === seatLabel);
  const streams = await Promise.all(
    crews.map((crew) => recordAdapter.sessionStream(crew.sessionName))
  );
  return crews.map((crew, index) => ({
    crew,
    stream: streams[index] ?? {
      state: "unavailable",
      failure: {
        reason: "no pane read was attempted for this tab",
        failureClass: "permanent",
        attempts: 0,
        elapsedMs: 0,
        status: null,
      },
    },
  }));
}
