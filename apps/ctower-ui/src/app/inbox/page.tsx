import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { recordAdapter, SOURCE_LABELS } from "@/read/adapter";
import { clockText, dayText } from "@/read/elapsed";
import type { InboxMessage, SeatInbox, TailNote } from "@/read/interface";
import { ChoiceTabs } from "@/surfaces/ChoiceTabs";
import { readParam } from "@/surfaces/screenParams";
import { severityClass, severityLabel } from "@/surfaces/severity";

export const dynamic = "force-dynamic";

function Message({ message }: { readonly message: InboxMessage }): ReactElement {
  return (
    <div className={message.read ? "msg" : "msg unread"}>
      <span className="dot" />
      <div className="subj">{message.subject}</div>
      <div className="when">
        {dayText(message.at)} {clockText(message.at)}
      </div>
      <div className="meta">
        <span className={severityClass(message.severity)}>{severityLabel(message.severity)}</span>
        <span>from {message.from}</span>
        {message.project === null ? null : <span>{message.project}</span>}
        <span>{message.read ? "read" : "unread"}</span>
        {message.wasRedacted ? <span>redacted before render</span> : null}
      </div>
      {message.body === null || message.body === message.subject ? null : (
        <div className="body">
          <p>{message.body}</p>
        </div>
      )}
    </div>
  );
}

/** What a mid-write tail did to this read, stated rather than hidden. */
function TailLine({ tail }: { readonly tail: TailNote }): ReactElement {
  const notes = [
    `${tail.totalLines.toString()} complete lines`,
    tail.partialTail ? "1 line at the tail was mid-write and is not shown" : "no partial tail",
    tail.malformed === 0 ? "none malformed" : `${tail.malformed.toString()} malformed`,
  ];
  return <span>{notes.join(" · ")}</span>;
}

function InboxBody({ inbox }: { readonly inbox: SeatInbox }): ReactElement {
  const unread = inbox.messages.filter((message) => !message.read).length;
  return (
    <>
      <Chrome section="Inbox" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Inbox</h1>
            <p>
              Each seat has one durable inbox. Messages are addressed to the seat by name, never to
              a session, so a compaction or a closed tab cannot lose one — and the read cursor is
              the seat&rsquo;s, not the reader&rsquo;s.
            </p>
          </div>

          {/* the tab counts unread and says so on the tab. A seat with 485 read
              messages reads as "0 unread", not as an empty inbox (#239) */}
          <ChoiceTabs
            label="Choose a seat"
            route="/inbox"
            selected={inbox.selected}
            choices={inbox.seats.map((seat) => ({
              key: seat.seat,
              label: seat.seat,
              count: {
                value: seat.unread,
                unit: "unread",
                detail: `${seat.unread.toString()} unread of ${seat.total.toString()} this seat holds`,
              },
              title: `${seat.total.toString()} messages · ${seat.unread.toString()} unread`,
            }))}
          />

          <div className="addr">
            <span className="k">Address as</span>
            <span className="name">{inbox.selected}</span>
            <span className="how">{inbox.addressing}</span>
          </div>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Messages</h2>
              {/* both numbers name what they count: the panel's is the seat's
                  total held, the tab's is its unread, and they no longer sit a
                  few pixels apart meaning different things (#239) */}
              <span className="sub">
                showing {inbox.messages.length.toString()} newest of {inbox.held.toString()}{" "}
                messages this seat holds · {unread.toString()} of them unread
              </span>
            </header>
            <div>
              {inbox.messages.map((message) => (
                <Message
                  key={`${message.at}-${message.from}-${message.subject}`}
                  message={message}
                />
              ))}
            </div>
          </section>

          <RecordFoot readPath={SOURCE_LABELS.inbox} watermark={<TailLine tail={inbox.tail} />} />
        </div>
      </main>
    </>
  );
}

function InboxFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Inbox" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Inbox</h1>
            <p>Each seat has one durable inbox, addressed by name.</p>
          </div>
          <div className="addr">
            <span className="k">Address as</span>
            <span className="name">—</span>
            <span className="how">
              the seat addressing name and the exact line that reaches it are the loudest thing on
              this screen once a source answers
            </span>
          </div>
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Messages</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath={SOURCE_LABELS.inbox} />
        </div>
      </main>
    </>
  );
}

export default async function InboxPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const inbox = await recordAdapter.seatInbox(readParam(await searchParams, "seat"));
  return (
    <Resolved reading={inbox} frame={(declared) => <InboxFrame declared={declared} />}>
      {(value) => <InboxBody inbox={value} />}
    </Resolved>
  );
}
