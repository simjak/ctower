import { read } from "./httpRecordAdapter";
import {
  asArray,
  asInteger,
  asIntegerOrNull,
  asRecord,
  asString,
  asStringOrNull,
  PayloadRefusal,
} from "./json";
import { reading } from "./outcome";
import type { Reading, WorkSession } from "./interface";

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
 * A ticket with no sessions is an answered *silence* — the record answered and
 * holds none — which is a different claim from the one the screen used to make,
 * and the reason this module exists rather than a citation being edited.
 */

/**
 * Token usage, which the contract makes nullable and the kernel emits as null
 * for a session that has recorded none yet.
 *
 * This was the one nullable field read with a non-null reader. `asRecord`
 * throws on null, the throw escapes the `.map` over every row, and `reading()`
 * turns the whole read into a failure — so a single in-flight session with no
 * usage recorded blanked both the ticket work timeline and the crew cost panel,
 * neither of which had anything wrong with them. The null branch is an answered
 * absence and reads as zeroes; the non-null branch stays strict, so a malformed
 * usage object is still refused rather than defaulted.
 */
function tokensOf(value: unknown): {
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly totalTokens: number;
} {
  if (value === null || value === undefined) {
    return { inputTokens: 0, outputTokens: 0, totalTokens: 0 };
  }
  const tokens = asRecord(value, "ticket.sessions[].tokens");
  return {
    inputTokens: asInteger(tokens.input_tokens, "ticket.sessions[].tokens.input_tokens"),
    outputTokens: asInteger(tokens.output_tokens, "ticket.sessions[].tokens.output_tokens"),
    totalTokens: asInteger(tokens.total_tokens, "ticket.sessions[].tokens.total_tokens"),
  };
}

export function toWorkSession(value: unknown): WorkSession {
  const row = asRecord(value, "ticket.sessions[]");
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
    ...tokensOf(row.tokens),
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
/**
 * The most pages this will walk before it stops asking.
 *
 * The route pages at the contract's maximum of 100, so this covers 5000
 * recorded sessions on one project. It is a bound, not an expectation: an
 * unbounded follow would hand a paging bug on the record's side an unbounded
 * read on this side.
 */
const SESSION_PAGE_CAP = 50;
const SESSION_PAGE_SIZE = 100;

/**
 * Every recorded session on a project, followed to exhaustion.
 *
 * The first version made one request and read `sessions`, silently dropping
 * `next_cursor` — so past one page the cost panel stated a confident total that
 * was a fraction of the truth, which is exactly the failure that panel's own
 * reason for existing is to prevent. A cursor the record hands back is a
 * statement that there is more, and this follows it.
 *
 * The page cap is deliberate and would be a lie to hide: if it is ever reached
 * the read refuses rather than returning a short answer that looks complete.
 */
async function loadProjectSessions(projectKey: string): Promise<readonly WorkSession[]> {
  const sessions: WorkSession[] = [];
  let cursor: number | null = 0;
  for (let page = 0; page < SESSION_PAGE_CAP; page += 1) {
    const path =
      `/v1/projects/${encodeURIComponent(projectKey)}/sessions` +
      `?cursor=${String(cursor)}&limit=${String(SESSION_PAGE_SIZE)}`;
    const row = asRecord(await read(path), "project.sessions");
    sessions.push(...asArray(row.sessions, "project.sessions.sessions").map(toWorkSession));
    cursor = asIntegerOrNull(row.next_cursor, "project.sessions.next_cursor");
    if (cursor === null) {
      return sessions;
    }
  }
  throw new PayloadRefusal(
    "project.sessions.next_cursor",
    `exhausted within ${String(SESSION_PAGE_CAP)} pages; the record is still offering more`
  );
}

async function loadCrewSessions(
  projectKey: string,
  crewName: string
): Promise<readonly WorkSession[]> {
  const sessions = await loadProjectSessions(projectKey);
  return sessions.filter((session) => session.crewName === crewName);
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
