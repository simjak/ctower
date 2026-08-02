import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";
import { DeclaredState, NoSourceYet } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter } from "@/read/adapter";
import { shortId } from "@/read/elapsed";
import type { RecordEvent, Reading, TicketRecord } from "@/read/interface";
import { Composer } from "@/surfaces/feed/Composer";
import { focusTicket } from "@/surfaces/feed/focus";
import { FeedViews } from "@/surfaces/feed/FeedViews";
import { ChatThread, RawStream } from "@/surfaces/feed/Thread";
import { workflowRefOf } from "@/surfaces/record/events";

export const dynamic = "force-dynamic";

const SESSION_FACTS = {
  lands: "G5",
  what: "agent turns, their reasoning, their tool calls, and the seat, model, token cost and live duration of a session",
} as const;

function Lede(): ReactElement {
  return (
    <div className="lede">
      <h1>Live feed</h1>
      <p>
        The session as a conversation: what it decided, what it ran, and every turn an operator or
        commander put into it. Tool calls collapse into the flow so the reasoning stays readable,
        and the raw terminal is one switch away when something needs debugging.
      </p>
    </div>
  );
}

function FeedFallback<T>({ reading }: { readonly reading: Reading<T> }): ReactElement {
  return (
    <>
      <Chrome section="Feed" />
      <main className="page">
        <div className="wrap">
          <Lede />
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Stream</h2>
            </header>
            <DeclaredState reading={reading} />
            <Composer />
          </section>
          <RecordFoot />
        </div>
      </main>
    </>
  );
}

function SessionMeta({
  ticket,
  events,
}: {
  readonly ticket: TicketRecord;
  readonly events: readonly RecordEvent[];
}): ReactElement {
  const workflow = workflowRefOf(events);
  return (
    <>
      <span className="av" style={{ width: "27px", height: "27px", fontSize: "10.5px" }}>
        RC
      </span>
      <span>
        <span className="who">record stream</span>{" "}
        <span className="crew">ticket {shortId(ticket.ticketId)}</span>
      </span>
      <span className="chip">{ticket.source.kind}</span>
      {workflow === null ? null : <span className="chip">{workflow}</span>}
      <span className="verdict v-held">no session recorded</span>
    </>
  );
}

export default async function FeedPage(): Promise<ReactElement> {
  const board = await recordAdapter.board();
  if (board.state !== "present") {
    return <FeedFallback reading={board} />;
  }
  const focus = await focusTicket(board.value);
  if (focus === null) {
    return (
      <FeedFallback
        reading={{
          state: "absent",
          source: { lands: "G5", what: "any recorded activity to render as a thread" },
        }}
      />
    );
  }
  const ticket = await recordAdapter.ticket(focus.ticketId);
  if (ticket.state !== "present") {
    return <FeedFallback reading={ticket} />;
  }

  const events = focus.events;
  return (
    <>
      <Chrome section="Feed" />
      <main className="page">
        <div className="wrap">
          <Lede />
          <section className="panel" style={{ marginTop: "16px" }}>
            <FeedViews
              sessionMeta={<SessionMeta ticket={ticket.value} events={events} />}
              chat={
                <>
                  <NoSourceYet title="no session data yet" source={SESSION_FACTS} />
                  <ChatThread events={events} />
                </>
              }
              raw={
                <>
                  <NoSourceYet title="no session data yet" source={SESSION_FACTS} />
                  <RawStream events={events} />
                </>
              }
            />
            <Composer />
          </section>
          <RecordFoot
            readPath={`/v1/tickets/${shortId(ticket.value.ticketId)}/audit`}
            watermark={`${events.length.toString()} appended events · the thread is the record, not a session`}
          />
        </div>
      </main>
    </>
  );
}
