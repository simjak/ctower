import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { InlineReading, NoSourceYet, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter } from "@/read/adapter";
import { shortId } from "@/read/elapsed";
import { feedFocus } from "@/read/feedFocus";
import type { FeedFocus } from "@/read/feedFocus";
import type { Reading, RecordEvent, TicketRecord } from "@/read/interface";
import { Composer } from "@/surfaces/feed/Composer";
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

function FeedFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
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
            {declared}
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
  readonly ticket: Reading<TicketRecord>;
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
        <InlineReading
          reading={ticket}
          present={(value) => <span className="crew">ticket {shortId(value.ticketId)}</span>}
          missing={(label, detail, tone) => (
            <span className="crew" style={tone} title={detail}>
              ticket {label}
            </span>
          )}
        />
      </span>
      <InlineReading
        reading={ticket}
        present={(value) => <span className="chip">{value.source.kind}</span>}
        missing={(label, detail, tone) => (
          <span className="chip" style={tone} title={detail}>
            source {label}
          </span>
        )}
      />
      {workflow === null ? null : <span className="chip">{workflow}</span>}
      <span className="verdict v-held">no session recorded</span>
    </>
  );
}

function FeedBody({
  focus,
  ticket,
}: {
  readonly focus: FeedFocus;
  readonly ticket: Reading<TicketRecord>;
}): ReactElement {
  const events = focus.events;
  return (
    <>
      <Chrome section="Feed" />
      <main className="page">
        <div className="wrap">
          <Lede />
          <section className="panel" style={{ marginTop: "16px" }}>
            <FeedViews
              sessionMeta={<SessionMeta ticket={ticket} events={events} />}
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
            readPath={`/v1/tickets/${shortId(focus.ticketId)}/audit`}
            watermark={`${events.length.toString()} appended events · the thread is the record, not a session`}
          />
        </div>
      </main>
    </>
  );
}

async function FocusedFeed({ focus }: { readonly focus: FeedFocus }): Promise<ReactElement> {
  return <FeedBody focus={focus} ticket={await recordAdapter.ticket(focus.ticketId)} />;
}

export default async function FeedPage(): Promise<ReactNode> {
  const focus = await feedFocus();
  return (
    <Resolved reading={focus} frame={(declared) => <FeedFrame declared={declared} />}>
      {(value) => <FocusedFeed focus={value} />}
    </Resolved>
  );
}
