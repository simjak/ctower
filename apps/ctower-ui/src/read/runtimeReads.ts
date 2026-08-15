import { recordCadenceRegistry } from "./beatRegistry";
import { read } from "./httpRecordAdapter";
import { asArray, asInteger, asIntegerOrNull, asRecord, asString, asStringOrNull } from "./json";
import { reading } from "./outcome";
import type { BeatDispatchRead, BeatRoutineRead } from "./beatRegistry";
import type { CadenceRegistry, Reading, WorkSession } from "./interface";

/**
 * The two record reads that replaced a declared absence.
 *
 * Both facts used to be things ctower did not carry, so the screens above them
 * rendered the "no data source yet" block and named the work that would land
 * one. The record carries them now:
 *
 * * `GET /v1/tickets/{id}/sessions` answers with the ticket's ordered work
 *   sessions — seat, crew, model, duration, tokens and outcome, which is the
 *   approved work timeline column for column;
 * * `GET /v1/runtime/beat-routines` and `GET /v1/runtime/beat-dispatches`
 *   answer with every registered cadence revision, the server's own next fire,
 *   and the immutable effects each has emitted.
 *
 * A ticket with no sessions and a routine with no dispatch are now *silences* —
 * the record answered and holds none — which is a different claim from the one
 * those screens were making, and the reason this module exists rather than a
 * citation being edited.
 */

/** The label the provenance foot prints for the cadence screen. */
export const CADENCE_SOURCE_LABEL =
  "ctower read API · /v1/runtime/beat-routines + /v1/runtime/beat-dispatches";

function toWorkSession(value: unknown): WorkSession {
  const row = asRecord(value, "ticket.sessions[]");
  const tokens = asRecord(row.tokens, "ticket.sessions[].tokens");
  return {
    sessionId: asString(row.session_id, "ticket.sessions[].session_id"),
    crewName: asString(row.crew_name, "ticket.sessions[].crew_name"),
    seatKey: asString(row.seat_key, "ticket.sessions[].seat_key"),
    projectKey: asString(row.project_key, "ticket.sessions[].project_key"),
    modelRef: asString(row.model_ref, "ticket.sessions[].model_ref"),
    harnessRef: asString(row.harness_ref, "ticket.sessions[].harness_ref"),
    branchRef: asString(row.branch_ref, "ticket.sessions[].branch_ref"),
    worktreeRef: asString(row.worktree_ref, "ticket.sessions[].worktree_ref"),
    state: asString(row.state, "ticket.sessions[].state"),
    outcome: asStringOrNull(row.outcome, "ticket.sessions[].outcome"),
    startedAt: asString(row.started_at, "ticket.sessions[].started_at"),
    closedAt: asStringOrNull(row.closed_at, "ticket.sessions[].closed_at"),
    durationSeconds: asIntegerOrNull(row.duration_seconds, "ticket.sessions[].duration_seconds"),
    inputTokens: asInteger(tokens.input_tokens, "ticket.sessions[].tokens.input_tokens"),
    outputTokens: asInteger(tokens.output_tokens, "ticket.sessions[].tokens.output_tokens"),
    totalTokens: asInteger(tokens.total_tokens, "ticket.sessions[].tokens.total_tokens"),
    transitionCount: asInteger(row.transition_count, "ticket.sessions[].transition_count"),
    evidenceRef: asStringOrNull(row.evidence_ref, "ticket.sessions[].evidence_ref"),
  };
}

async function loadWorkSessions(
  ticketId: string,
  projectKey: string
): Promise<readonly WorkSession[]> {
  const path = `/v1/tickets/${encodeURIComponent(ticketId)}/sessions?project_key=${encodeURIComponent(projectKey)}`;
  const row = asRecord(await read(path), "ticket.sessions");
  return asArray(row.sessions, "ticket.sessions.sessions").map(toWorkSession);
}

function toRoutine(value: unknown): BeatRoutineRead {
  const row = asRecord(value, "runtime.beat-routines[]");
  const schedule = asRecord(row.schedule, "runtime.beat-routines[].schedule");
  const hours = schedule.hours;
  return {
    routineRef: asString(row.routine_ref, "runtime.beat-routines[].routine_ref"),
    beatKey: asString(row.beat_key, "runtime.beat-routines[].beat_key"),
    targetSession: asString(row.target_session, "runtime.beat-routines[].target_session"),
    nextFireAt: asString(row.next_fire_at, "runtime.beat-routines[].next_fire_at"),
    minutes: asArray(schedule.minutes, "runtime.beat-routines[].schedule.minutes").map(
      (minute, index) =>
        asInteger(minute, `runtime.beat-routines[].schedule.minutes[${index.toString()}]`)
    ),
    hours:
      hours === null || hours === undefined
        ? null
        : asArray(hours, "runtime.beat-routines[].schedule.hours").map((hour, index) =>
            asInteger(hour, `runtime.beat-routines[].schedule.hours[${index.toString()}]`)
          ),
    timezone: asString(schedule.timezone, "runtime.beat-routines[].schedule.timezone"),
  };
}

function toDispatch(value: unknown): BeatDispatchRead {
  const row = asRecord(value, "runtime.beat-dispatches[]");
  return {
    routineRef: asString(row.routine_ref, "runtime.beat-dispatches[].routine_ref"),
    emittedAt: asString(row.emitted_at, "runtime.beat-dispatches[].emitted_at"),
  };
}

async function loadCadenceRegistry(): Promise<CadenceRegistry> {
  const [registered, emitted] = await Promise.all([
    read("/v1/runtime/beat-routines"),
    read("/v1/runtime/beat-dispatches"),
  ]);
  const routines = asArray(
    asRecord(registered, "runtime.beat-routines").routines,
    "runtime.beat-routines.routines"
  ).map(toRoutine);
  const dispatches = asArray(
    asRecord(emitted, "runtime.beat-dispatches").effects,
    "runtime.beat-dispatches.effects"
  ).map(toDispatch);
  return recordCadenceRegistry(
    routines,
    dispatches,
    CADENCE_SOURCE_LABEL,
    new Date().toISOString()
  );
}

/**
 * One crew's recorded sessions across a project.
 *
 * The crew profile's cost panel used to print `— · —` and cite the work that
 * would land a per-session cost. The record carries it; the join is the
 * session's own `crew_name`, so this asks the project page and keeps the rows
 * that name this crew. A crew whose project the profile could not establish has
 * nothing to scope the read by, and that is the caller's decision to make, not
 * this module's — it takes a project key or it is not called.
 */
async function loadCrewSessions(
  projectKey: string,
  crewName: string
): Promise<readonly WorkSession[]> {
  const path = `/v1/projects/${encodeURIComponent(projectKey)}/sessions`;
  const row = asRecord(await read(path), "project.sessions");
  return asArray(row.sessions, "project.sessions.sessions")
    .map(toWorkSession)
    .filter((session) => session.crewName === crewName);
}

export async function readCrewSessions(
  projectKey: string,
  crewName: string
): Promise<Reading<readonly WorkSession[]>> {
  return await reading(async () => await loadCrewSessions(projectKey, crewName));
}

export async function readWorkSessions(
  ticketId: string,
  projectKey: string
): Promise<Reading<readonly WorkSession[]>> {
  return await reading(async () => await loadWorkSessions(ticketId, projectKey));
}

export async function readCadenceRegistry(): Promise<Reading<CadenceRegistry>> {
  return await reading(loadCadenceRegistry);
}
