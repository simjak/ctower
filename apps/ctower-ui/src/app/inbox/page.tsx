import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { SOURCE_LABELS, recordAdapter } from "@/read/adapter";
import { shortId, stampText } from "@/read/elapsed";
import type {
  InboxCorrespondent,
  InboxCorrespondents,
  InboxProjection,
  InboxThread,
  InboxThreadSummary,
  Reading,
} from "@/read/interface";
import { Count } from "@/surfaces/Count";
import { readParam } from "@/surfaces/screenParams";
import { composeThreadAction, promoteThreadAction, sendMessageAction } from "./actions";
import { ComposeThread } from "@/surfaces/inbox/ComposeThread";
import { PromoteThread } from "@/surfaces/inbox/PromoteThread";
import { SendMessage } from "@/surfaces/inbox/SendMessage";
import { ThreadMessage } from "@/surfaces/inbox/ThreadMessage";

export const dynamic = "force-dynamic";

function threadHref(threadId: string): string {
  return `/inbox?thread=${encodeURIComponent(threadId)}`;
}

function ticketHref(ticketId: string): string {
  return `/ticket/${encodeURIComponent(ticketId)}`;
}

function TicketLink({ ticketId }: { readonly ticketId: string }): ReactElement {
  return (
    <Link className="name" href={ticketHref(ticketId)}>
      ticket {shortId(ticketId)}
    </Link>
  );
}

function ThreadRow({ thread }: { readonly thread: InboxThreadSummary }): ReactElement {
  const unread = thread.unreadCount > 0;
  return (
    <Link className={unread ? "msg unread" : "msg"} href={threadHref(thread.threadId)}>
      <span className="dot" />
      <div className="subj">{thread.lastMessagePreview}</div>
      <div className="when">{stampText(thread.lastMessageAt)}</div>
      <div className="meta">
        <span>with {thread.otherAgent}</span>
        <Count
          value={thread.unreadCount}
          unit="unread"
          detail={`${thread.unreadCount.toString()} unread messages in this thread`}
        />
        {thread.promotedTicketId === null ? null : <span>ticket linked</span>}
        <span className="mono">thread {shortId(thread.threadId)}</span>
      </div>
    </Link>
  );
}

function InboxList({
  inbox,
  correspondents,
}: {
  readonly inbox: InboxProjection;
  readonly correspondents: Reading<InboxCorrespondents>;
}): ReactElement {
  return (
    <>
      <Chrome section="Inbox" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Inbox</h1>
            <p>
              Durable threads addressed to this principal, with unread state from the projection.
            </p>
          </div>

          <div className="addr">
            <span className="k">Addressed to</span>
            <span className="name">{inbox.recipient}</span>
            <span className="how">recipient-scoped inbox projection</span>
          </div>

          <Resolved brief reading={correspondents} subject="the seats you can write to">
            {(value) => <ComposeThread action={composeThreadAction} correspondents={value} />}
          </Resolved>

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Threads</h2>
              <span className="sub">
                {inbox.threads.length.toString()} threads · {inbox.totalUnread.toString()} unread
              </span>
            </header>
            {inbox.threads.length === 0 ? (
              <div className="body">
                <p>The record answered: no threads are addressed to this principal.</p>
              </div>
            ) : (
              <div>
                {inbox.threads.map((thread) => (
                  <ThreadRow key={thread.threadId} thread={thread} />
                ))}
              </div>
            )}
          </section>

          <RecordFoot readPath={SOURCE_LABELS.inbox} />
        </div>
      </main>
    </>
  );
}

function InboxThreadBody({
  thread,
  picker,
  correspondent,
}: {
  readonly thread: InboxThread;
  readonly picker: Awaited<ReturnType<typeof recordAdapter.inboxPromotionPicker>>;
  readonly correspondent: Reading<InboxCorrespondent>;
}): ReactElement {
  const promote = promoteThreadAction.bind(null, thread.threadId);
  const send = sendMessageAction.bind(null, thread.threadId);
  return (
    <>
      <Chrome section="Inbox" back={{ href: "/inbox", label: "Inbox" }} />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Thread</h1>
            <p>
              Ordered durable messages for this recipient. Opening the thread updates only this
              recipient&rsquo;s read cursor.
            </p>
          </div>

          <div className="addr">
            <span className="k">Participants</span>
            <span className="name">{thread.participants.join(" · ")}</span>
            <span className="how">thread {thread.threadId}</span>
          </div>

          {thread.promotedTicketId === null ? null : (
            <div className="addr">
              <span className="k">Promoted ticket</span>
              <TicketLink ticketId={thread.promotedTicketId} />
              <span className="how">immutable inbox-to-ticket link from the projection</span>
            </div>
          )}

          {thread.promotedTicketId === null ? (
            <PromoteThread action={promote} choices={picker.choices} pickerNotice={picker.notice} />
          ) : null}

          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Messages</h2>
              <span className="sub">
                {thread.messages.length.toString()} messages · read through{" "}
                {thread.readThroughPosition.toString()}
              </span>
            </header>
            <div>
              {thread.messages.map((message) => (
                <ThreadMessage key={message.messageId} message={message} />
              ))}
            </div>
            <Resolved brief reading={correspondent} subject="the seats this thread is between">
              {(value) => (
                <SendMessage
                  action={send}
                  correspondent={value}
                  settled={thread.messages.map((message) => message.messageId)}
                />
              )}
            </Resolved>
          </section>

          <RecordFoot readPath={SOURCE_LABELS.inbox} />
        </div>
      </main>
    </>
  );
}

function InboxListFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Inbox" />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Inbox</h1>
            <p>Durable threads addressed to this principal.</p>
          </div>
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>Threads</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath={SOURCE_LABELS.inbox} />
        </div>
      </main>
    </>
  );
}

function InboxThreadFrame({ declared }: { readonly declared: ReactElement }): ReactElement {
  return (
    <>
      <Chrome section="Inbox" back={{ href: "/inbox", label: "Inbox" }} />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Thread</h1>
            <p>Ordered durable messages for this recipient.</p>
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
  const threadId = readParam(await searchParams, "thread");
  if (threadId !== null) {
    const [thread, picker, correspondent] = await Promise.all([
      recordAdapter.inboxThread(threadId),
      recordAdapter.inboxPromotionPicker(),
      recordAdapter.inboxCorrespondent(threadId),
    ]);
    return (
      <Resolved reading={thread} frame={(declared) => <InboxThreadFrame declared={declared} />}>
        {(value) => (
          <InboxThreadBody correspondent={correspondent} picker={picker} thread={value} />
        )}
      </Resolved>
    );
  }
  const [inbox, correspondents] = await Promise.all([
    recordAdapter.inbox(),
    recordAdapter.inboxCorrespondents(),
  ]);
  return (
    <Resolved reading={inbox} frame={(declared) => <InboxListFrame declared={declared} />}>
      {(value) => <InboxList correspondents={correspondents} inbox={value} />}
    </Resolved>
  );
}
