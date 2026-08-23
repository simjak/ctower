import type { ReactElement } from "react";
import type { AssignmentInterval, AssignmentKind, TicketSession } from "@ctower/client";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import { Hint } from "../../ui/form";
import { livenessOf } from "../../cockpit/liveness";
import { Asking, Malformed, Refused, Unreachable } from "../../wizard/states";
import type { Answer } from "../../api/client";
import { useTicketCrew } from "./reads";

/**
 * The crew on this ticket: who holds it, and who is working it.
 *
 * Both halves are the record's own answers to two declared reads —
 * `listTicketAssignments` and `listTicketSessions` — and the difference between
 * them is the point. An assignment is who the record says holds this; a session
 * is what a crew is actually doing about it, on which branch, with which model.
 * A ticket can have either without the other, so neither half speaks for the
 * other and neither borrows the other's silence.
 *
 * One thing is deliberately not drawn: **who the assigned principal is**. The
 * record answers with a `principal_id` and the authored contract has no
 * operation that turns one into a name, a seat or a crew. Matching it against
 * the seat on a session would be a join nothing declares — the same invention
 * that has already been caught twice in this product — so the identifier is
 * shown as the identifier it is and the missing read is named.
 */
export function TicketCrew({
  projectKey,
  ticketId,
}: {
  readonly projectKey: string;
  readonly ticketId: string;
}): ReactElement {
  const crew = useTicketCrew(projectKey, ticketId);
  return (
    <>
      <Working sessions={crew.sessions} />
      <Holding assignments={crew.assignments} />
    </>
  );
}

function Working({
  sessions,
}: {
  readonly sessions: Answer<{ readonly sessions: readonly TicketSession[] }>;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Working on this</CardTitle>
        <span className="flex-1" />
        {sessions.kind === "answered" ? (
          <Mono className="text-muted">{sessions.value.sessions.length}</Mono>
        ) : null}
      </CardHeader>
      <CardBody className="space-y-3">
        <Outcome
          answer={sessions}
          asking="Reading this ticket's sessions"
          nothing="No session is recorded against this ticket."
        >
          {sessions.kind === "answered"
            ? sessions.value.sessions.map((session) => (
                <Session key={session.session_id} session={session} />
              ))
            : null}
        </Outcome>
        <p className="m-0 flex items-center gap-1.5 text-xs text-muted">
          A session says what was last recorded, not what is true this second.
          <Hint text="TicketSession carries no heartbeat: state and closed_at are the last facts written, and no read reports when a crew was last seen." />
        </p>
      </CardBody>
    </Card>
  );
}

/**
 * One session, drawn from the record and from nothing else.
 *
 * The mark is `cockpit/liveness.ts` — the same mapping the Crews page uses, so
 * one session cannot read as `working` here and something else there. A session
 * that closed without an outcome draws no mark at all: that is the record
 * disagreeing with itself, not a state.
 */
function Session({ session }: { readonly session: TicketSession }): ReactElement {
  const live = livenessOf(session);
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line pb-3 last:border-b-0 last:pb-0">
      {live.mark === null ? <span className="inline-block w-[1.4em]" /> : <Mark name={live.mark} />}
      <span className="text-sm font-medium text-fg">{session.crew_name}</span>
      <Chip>{live.word}</Chip>
      <span className="w-full pl-[1.4em] text-xs text-muted">
        <Fact label="seat" value={session.seat_key} />
        <Fact label="branch" value={session.branch_ref} />
        <Fact label="model" value={session.model_ref} />
        <Fact label="harness" value={session.harness_ref} />
        <Fact label="started" value={session.started_at.slice(0, 16).replace("T", " ")} />
        <Fact label="worktree" value={session.worktree_ref} />
      </span>
    </div>
  );
}

function Holding({
  assignments,
}: {
  readonly assignments: Answer<{ readonly assignments: readonly AssignmentInterval[] }>;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Who holds it</CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        <Outcome
          answer={assignments}
          asking="Reading this ticket's custody"
          nothing="No assignment is recorded against this ticket."
        >
          {assignments.kind === "answered"
            ? assignments.value.assignments.map((interval) => (
                <Assignment
                  key={`${interval.assignment_kind}-${String(interval.sequence)}`}
                  interval={interval}
                />
              ))
            : null}
        </Outcome>
        <p className="m-0 flex items-center gap-1.5 text-xs text-muted">
          An assignment records an identifier, and no read turns one into a name.
          <Hint text="Assignments carry principal_id. The authored contract declares no operation that reads a principal, so a name would have to be guessed from somewhere it was never recorded." />
        </p>
      </CardBody>
    </Card>
  );
}

const KIND: Readonly<Record<AssignmentKind, string>> = {
  ticket_custodian: "custodian",
  current_assignee: "assignee",
  stage_owner: "stage owner",
  reviewer_assignment: "reviewer",
  runner_lease_owner: "runner lease",
};

function Assignment({ interval }: { readonly interval: AssignmentInterval }): ReactElement {
  const current = interval.released_at === null;
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line pb-3 last:border-b-0 last:pb-0">
      {/* Held is a recorded fact and carries the mark; released is history and
          carries none, because "no longer held" is not a state of anything. */}
      {current ? <Mark name="done" /> : <span className="inline-block w-[1.4em]" />}
      <span className="text-sm font-medium text-fg">{KIND[interval.assignment_kind]}</span>
      {current ? <Chip tone="ok">held</Chip> : <Chip>released</Chip>}
      <span className="w-full pl-[1.4em] text-xs text-muted">
        <Fact label="principal" value={interval.principal_id} />
        <Fact label="since" value={interval.assigned_at.slice(0, 16).replace("T", " ")} />
        <Fact label="episode" value={String(interval.episode_number)} />
        <Fact label="reason" value={interval.reason} />
      </span>
    </div>
  );
}

/** One recorded field, quiet, on the line under what it belongs to. */
function Fact({ label, value }: { readonly label: string; readonly value: string }): ReactElement {
  return (
    <span className="mr-4 inline-block">
      {label} <Mono className="text-fg/80">{value}</Mono>
    </span>
  );
}

/**
 * What a read answered, in the record's own terms.
 *
 * An empty list and a read that never landed are different facts and are drawn
 * differently: absence is a sentence, and a refusal, an unreachable API or a
 * malformed answer is the shared state component the rest of this console uses.
 */
function Outcome({
  answer,
  asking,
  nothing,
  children,
}: {
  readonly answer: Answer<unknown>;
  readonly asking: string;
  readonly nothing: string;
  readonly children: ReactElement[] | null;
}): ReactElement {
  switch (answer.kind) {
    case "asking":
      return <Asking what={asking} />;
    case "refused":
      return <Refused problem={answer.problem} action="Nothing was read. Reload to ask again." />;
    case "unreachable":
      return <Unreachable detail={answer.detail} action="Reload to ask again." />;
    case "malformed":
      return <Malformed detail={answer.detail} />;
    case "answered":
      return children === null || children.length === 0 ? (
        <p className="m-0 text-sm text-muted">{nothing}</p>
      ) : (
        <div className="space-y-3">{children}</div>
      );
  }
}
