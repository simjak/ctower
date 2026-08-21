import type { CSSProperties, ReactElement, ReactNode } from "react";
import { InlineReading } from "@/frame/Declared";
import { stageOf } from "@/read/boardProjection";
import { shortId, stampText } from "@/read/elapsed";
import type { BoardCard, Reading, TicketRecord, WorkSession } from "@/read/interface";
import { mapReading } from "@/read/reading";
import { newestSession } from "@/read/runtimeReads";
import type { NewestSession } from "@/read/runtimeReads";

/**
 * The ticket bar: the key an operator quotes, how far the work has got, and
 * where the workflow has this ticket — one line, above everything else.
 *
 * The approved cockpit puts this line first because *what is this work for*
 * precedes every other question on a ticket screen, and it carries three things
 * and no more. Each of the three is a different kind of claim, and the bar's
 * whole job is to keep them from being read as each other:
 *
 * * **the key** is an identity. `display_key` is the per-project name a person
 *   quotes; `ticket_id` is the address. A ticket the record assigns no key
 *   shows the identifier it *does* carry, labelled as the identifier, because
 *   printing a UUID under the word "key" would be spelling one fact as another;
 * * **the session** is a position on a closed ladder. `SessionState` is
 *   `dispatched → briefed → working → gated` and nothing else, so the position
 *   is real and is drawn as four segments — the eye gets *how far along*
 *   without reading, and the one word that remains is the one that changes;
 * * **the stage** is a name, never a position. The board projection folds
 *   `workflow.changed` server-side and serves the ticket's current `stage_key`,
 *   so the name is a served fact and is shown. What no read serves is the
 *   *ordered stage list* a `workflow_ref` declares, and without it there is no
 *   "third of five" to draw — a fixed stepper here would be a guess about
 *   someone else's workflow definition. So the stage gets a word and the
 *   session gets the segments, which is the honest split between them.
 *
 * The title is deliberately not repeated here. The cockpit's bar carries one
 * because that screen has no heading; this screen's `h1` is directly below, and
 * the copy budget is spent on the two facts the page was not showing at all.
 */

/** `SessionState`, in the order the contract closes it. */
const SESSION_LADDER = ["dispatched", "briefed", "working", "gated"] as const;

const LADDER_HINT = "dispatched → briefed → working → gated";

const STAGE_HINT =
  "the stage the board projection recorded; the ordered stage list its workflow declares is served" +
  " by no read, so this is a name and not a position";

function stepClass(index: number, position: number): string {
  if (index < position) {
    return "done";
  }
  return index === position ? "now" : "";
}

/**
 * The four segments. They are geometry, not text: the state's own word sits
 * beside them and carries the meaning, so the segments are hidden from a screen
 * reader rather than announced as four empty elements.
 *
 * A state outside the closed ladder draws no segments at all. The record would
 * have to be running a session vocabulary this build does not know, and putting
 * an unknown value at an invented position is the guess this surface refuses.
 */
function SessionSteps({ state }: { readonly state: string }): ReactElement | null {
  const position = SESSION_LADDER.findIndex((name) => name === state);
  if (position < 0) {
    return null;
  }
  return (
    <span aria-hidden="true" className="steps" title={LADDER_HINT}>
      {SESSION_LADDER.map((name, index) => (
        <i className={stepClass(index, position)} key={name} />
      ))}
    </span>
  );
}

function sessionHint({ session, total }: NewestSession): string {
  const closed = session.closedAt === null ? "still open" : `closed ${stampText(session.closedAt)}`;
  const of = total === 1 ? "" : ` · newest of ${total.toString()} on this ticket`;
  return `${session.seatKey} · ${session.crewName} · started ${stampText(session.startedAt)} · ${closed}${of}`;
}

function Lifecycle(newest: NewestSession): ReactElement {
  return (
    <>
      <SessionSteps state={newest.session.state} />
      <span className="v" title={sessionHint(newest)}>
        {newest.session.state}
      </span>
      {newest.total > 1 ? <span className="of">{newest.total} sessions</span> : null}
    </>
  );
}

/** A cell that did not resolve. The two kinds of not-resolving stay two kinds. */
function missingCell(label: string, detail: string, tone: CSSProperties): ReactNode {
  return (
    <span className="v miss" style={tone} title={detail}>
      {label}
    </span>
  );
}

/**
 * The key, and which key it is.
 *
 * `display_key` is server-assigned and nullable, so a ticket written before the
 * instance assigned one has none. That ticket still has an identifier, and the
 * bar shows it under its own label rather than under the label of a fact the
 * record does not carry.
 */
function Identity({ ticket }: { readonly ticket: TicketRecord }): ReactElement {
  if (ticket.displayKey === null) {
    return (
      <>
        <span className="k">ticket</span>
        <span className="key" title={`the record assigns no display key · ${ticket.ticketId}`}>
          {shortId(ticket.ticketId)}
        </span>
      </>
    );
  }
  return (
    <>
      <span className="k">key</span>
      <span className="key" title={`ticket ${ticket.ticketId}`}>
        {ticket.displayKey}
      </span>
    </>
  );
}

export function TicketBar({
  ticket,
  card,
  sessions,
}: {
  readonly ticket: TicketRecord;
  readonly card: Reading<BoardCard>;
  readonly sessions: Reading<readonly WorkSession[]>;
}): ReactElement {
  return (
    <div className="tbar">
      <Identity ticket={ticket} />
      <span className="tbar-gap" />
      <span className="tbar-cell">
        <span className="k">session</span>
        <InlineReading
          reading={mapReading(sessions, newestSession)}
          present={Lifecycle}
          missing={missingCell}
        />
      </span>
      <span className="tbar-cell">
        <span className="k">stage</span>
        <InlineReading
          reading={stageOf(card)}
          present={(name) => (
            <span className="v" title={STAGE_HINT}>
              {name}
            </span>
          )}
          missing={missingCell}
        />
      </span>
    </div>
  );
}
