import { httpRecordAdapter } from "./httpRecordAdapter";
import { readCronCadence } from "./sources/cadenceCron";
import { readCrewRoster } from "./sources/crewRoster";
import { readDeliveryMetrics } from "./sources/delivery";
import { readSystemdCadence } from "./sources/cadenceSystemd";
import { readAuthoredFiles } from "./sources/gitTree";
import { readSeatInbox } from "./sources/inboxFile";
import { cadenceSourceName } from "./sources/paths";
import { readSessionStream, readSessionWorkspace } from "./sources/tmuxBridge";
import { readSessionWorktree } from "./sources/worktrees";
import { reading } from "./outcome";
import type {
  AuthoredFiles,
  CadenceRegistry,
  CrewRoster,
  SessionStream,
  RecordAdapter,
  Reading,
  SeatInbox,
  SessionWorkspace,
  SessionWorktree,
} from "./interface";

/**
 * The swap seam.
 *
 * One source per screen, each named here and nowhere else. A screen asks the
 * adapter for its reading and never learns which source answered, so replacing
 * a source is an edit to this file alone — the component-C pattern applied to
 * reads. Board and Ticket stay on the read-API source and swap to #211's typed
 * feed when it merges; the six wave-2 screens swap to their native sources the
 * same way.
 *
 * Every binding is read-only, and every one goes through `reading`, so a source
 * that refuses or cannot be reached arrives at its screen as a typed failure
 * rather than as an empty value.
 */

export type ScreenKey =
  | "board"
  | "ticket"
  | "inbox"
  | "heartbeats"
  | "files"
  | "workspace"
  | "explorer"
  | "feed"
  | "metrics"
  | "team";

/** Which source answers each screen today, for the provenance foot. */
export const SOURCE_LABELS: Readonly<Record<ScreenKey, string>> = {
  board: "ctower read API · /v1/board",
  ticket: "ctower read API · /v1/tickets/{id} + /audit",
  inbox: "mission-control state/inbox.jsonl",
  heartbeats:
    cadenceSourceName() === "systemd" ? "systemd user timers" : "host crontab + state markers",
  files: "git tree",
  workspace: "live tmux sessions + git",
  explorer: "git worktree list + diff",
  feed: "live tmux sessions · capture-pane",
  metrics: "git first-parent trunk history per project",
  team: "live tmux sessions + mission-control state/crew-log.jsonl + personas/",
};

function cadenceSource(): () => Promise<CadenceRegistry> {
  return cadenceSourceName() === "systemd" ? readSystemdCadence : readCronCadence;
}

export const recordAdapter: RecordAdapter = {
  instance: httpRecordAdapter.instance,
  board: httpRecordAdapter.board,
  ticket: httpRecordAdapter.ticket,
  ticketAudit: httpRecordAdapter.ticketAudit,
  workSessions: httpRecordAdapter.workSessions,

  cadenceRegistry: async (): Promise<Reading<CadenceRegistry>> => await reading(cadenceSource()),
  seatInbox: async (seat: string | null): Promise<Reading<SeatInbox>> =>
    await reading(async () => await readSeatInbox(seat)),
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
};
