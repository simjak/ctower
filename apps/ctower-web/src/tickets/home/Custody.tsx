import type { ReactElement } from "react";
import type { AssignmentInterval, AssignmentKind, TicketSession } from "@ctower/client";
import { harnessNamed } from "../../agents/harnesses";
import { useTicketCrew } from "../crew/reads";
import { clockWords, spanWords } from "../words";
import { Absent, Answered, Section } from "./parts";

/**
 * Who has had this ticket, and who is working it.
 *
 * Two reads, kept apart because they are two facts. An assignment is who the
 * record says holds it, in episodes with a start, an end and a reason; a
 * session is what a crew actually did about it, on which harness. A ticket can
 * have either without the other, so neither borrows the other's silence.
 *
 * **The person is not drawn.** Every assignment answers with a `principal_id`
 * and the authored contract declares no operation that turns one into a name.
 * Matching it against a seat on a session would be a join nothing declares, so
 * the episode says what was held and for how long, and the missing read is
 * named in one line.
 */
export function Custody({
  projectKey,
  ticketId,
  now,
}: {
  readonly projectKey: string;
  readonly ticketId: string;
  readonly now: number;
}): ReactElement {
  const crew = useTicketCrew(projectKey, ticketId);
  const held = crew.assignments.kind === "answered" ? crew.assignments.value.assignments : [];
  const sessions = crew.sessions.kind === "answered" ? crew.sessions.value.sessions : [];

  return (
    <Section title="Who has had it">
      <Answered answer={crew.assignments} asking="Reading who has held this">
        {held.length === 0 && sessions.length === 0 ? (
          <p className="m-0 text-sm text-muted">Nobody has been recorded as holding this yet.</p>
        ) : null}
        {held.map((interval) => (
          <Episode
            key={`${interval.assignment_kind}-${String(interval.sequence)}`}
            interval={interval}
            now={now}
          />
        ))}
      </Answered>
      {sessions.map((session) => (
        <Worked key={session.session_id} session={session} now={now} />
      ))}
      <Absent>ctower knows which crew is working. It cannot yet say which person.</Absent>
    </Section>
  );
}

/**
 * What each kind of custody is, as the job it does. These are the record's own
 * closed set said in the operator's language; nothing here invents a sixth.
 */
const HOLDING: Readonly<Record<AssignmentKind, string>> = {
  ticket_custodian: "Holding it",
  current_assignee: "Working it",
  stage_owner: "Owning this step",
  reviewer_assignment: "Reviewing it",
  runner_lease_owner: "Running it",
};

function Episode({
  interval,
  now,
}: {
  readonly interval: AssignmentInterval;
  readonly now: number;
}): ReactElement {
  const current = interval.released_at === null;
  return (
    <Line
      what={
        <>
          {current ? <b className="font-semibold">{HOLDING[interval.assignment_kind]}</b> : null}
          {current ? null : HOLDING[interval.assignment_kind]}
          {interval.reason === "" ? null : <span className="text-muted"> — {interval.reason}</span>}
        </>
      }
      when={
        interval.released_at === null
          ? `since ${clockWords(interval.assigned_at)}`
          : `${clockWords(interval.assigned_at)}–${clockWords(interval.released_at)} · ${spanWords(elapsed(interval, now))}`
      }
    />
  );
}

function elapsed(interval: AssignmentInterval, now: number): number {
  const from = Date.parse(interval.assigned_at);
  const to = interval.released_at === null ? now : Date.parse(interval.released_at);
  return Number.isFinite(from) && Number.isFinite(to) ? Math.max(0, (to - from) / 1000) : 0;
}

/**
 * One crew's turn at the work. The harness is named only when this console can
 * say honestly which one it is; an adapter it does not know gets no name rather
 * than its own machine text dressed up as one.
 */
function Worked({
  session,
  now,
}: {
  readonly session: TicketSession;
  readonly now: number;
}): ReactElement {
  const harness = harnessNamed(session.harness_ref);
  const open = session.closed_at === null;
  return (
    <Line
      what={
        <>
          <b className="font-semibold">{session.crew_name}</b>
          {harness === null ? null : <span className="text-muted"> — on {harness}</span>}
        </>
      }
      when={
        open
          ? `since ${clockWords(session.started_at)}`
          : spanWords(session.duration_seconds ?? ranFor(session, now))
      }
    />
  );
}

function ranFor(session: TicketSession, now: number): number {
  const from = Date.parse(session.started_at);
  const to = session.closed_at === null ? now : Date.parse(session.closed_at);
  return Number.isFinite(from) && Number.isFinite(to) ? Math.max(0, (to - from) / 1000) : 0;
}

/** One episode on its own line: what was held on the left, when on the right. */
function Line({
  what,
  when,
}: {
  readonly what: ReactElement;
  readonly when: string;
}): ReactElement {
  return (
    <div className="flex items-baseline gap-4 border-t border-line py-2.5 text-sm first:border-t-0">
      <span className="min-w-0 flex-1">{what}</span>
      <span className="shrink-0 text-xs whitespace-nowrap text-muted">{when}</span>
    </div>
  );
}
