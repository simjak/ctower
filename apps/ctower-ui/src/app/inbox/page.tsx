import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { Resolved } from "@/frame/Declared";
import { recordAdapter } from "@/read/adapter";
import { cardFor } from "@/read/boardProjection";
import { defaultProjectKey } from "@/read/projects";
import { ChatComposer } from "@/surfaces/chat/Composer";
import { LinkTicket } from "@/surfaces/chat/LinkTicket";
import { NewThread } from "@/surfaces/chat/NewThread";
import { SessionPane } from "@/surfaces/chat/SessionPane";
import { ThreadHead } from "@/surfaces/chat/ThreadHead";
import { ThreadList } from "@/surfaces/chat/ThreadList";
import { Transcript } from "@/surfaces/chat/Transcript";
import { WorkPanel } from "@/surfaces/chat/WorkPanel";
import { NothingGlyph } from "@/surfaces/chat/glyphs";
import { readParam } from "@/surfaces/screenParams";
import { composeThreadAction, promoteThreadAction, sendMessageAction } from "./actions";
import type { WorkTab } from "@/surfaces/chat/WorkPanel";
import type {
  InboxCorrespondents,
  InboxDelivery,
  InboxProjection,
  InboxThread,
  Reading,
} from "@/read/interface";

export const dynamic = "force-dynamic";

/**
 * The chat workspace.
 *
 * The operator rejected the screen this replaces — a lede paragraph, a wrapped
 * row of seat pills, a panel whose loudest element was a shell command, and
 * every message drawn as an identical prose card. He named the shape he wants
 * instead: conversations down the left, the transcript in the middle with the
 * box under it, and what the conversation is *about* on the right, with the
 * live session beneath that.
 *
 * Every pane is a recorded fact and every control asks a real,
 * server-authorized operation. The box sends through `POST /v1/inbox/messages`,
 * the new-conversation control through `POST /v1/inbox/notifications`, and the
 * link control through `POST /v1/inbox/threads/{id}/promotion` — this surface
 * is not read-only, and nothing on it is a placeholder.
 *
 * The browser still holds nothing. Every read and every command runs server
 * side; no credential, session or token reaches the page.
 */

const TABS: readonly WorkTab[] = ["changes", "checks", "review"];
const NO_ADDRESS =
  "this server's principal holds no registered seat, so it has no address to write from";
const NO_SEATS = "the record lists no seat this server can write to";
/** The record's own name for a principal that holds no seat row. */
const UNADDRESSABLE = "unaddressable";
/** What mints a principal with a seat row — the one action that gives it an address. */
const SEAT_COMMAND = "ctowerctl credential seat issue";
/**
 * A conversation with no message has no delivery truth to read, and the record
 * refuses a read-state request for one. That is an answered emptiness, not a
 * failed read, so it is declared as a silence rather than sent to the instance.
 */
const EMPTY_DELIVERY: Reading<InboxDelivery> = {
  state: "absent",
  source: { absence: "silence", what: "delivery event on a conversation holding no message" },
};

function tabOf(requested: string | null): WorkTab {
  return TABS.find((tab) => tab === requested) ?? "changes";
}

/** A shell with the frame and the conversation list around whatever the middle is. */
function Workspace({
  inbox,
  correspondents,
  openThreadId,
  detail,
  now,
  children,
}: {
  /** `null` while the projection itself did not answer: no list to draw. */
  readonly inbox: InboxProjection | null;
  readonly correspondents: Reading<InboxCorrespondents>;
  readonly openThreadId: string | null;
  /** Whether the reader has opened one conversation: master, or detail. */
  readonly detail: boolean;
  readonly now: number;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <>
      <Chrome back={detail ? { href: "/inbox", label: "Conversations" } : null} section="Inbox" />
      <main className={detail ? "cw detail" : "cw"}>
        {inbox === null ? null : (
          <Resolved brief reading={correspondents} subject="the seats you can write to">
            {(value) => (
              <ThreadList
                canCompose={value.choices.length > 0}
                composeReason={value.sender === "unaddressable" ? NO_ADDRESS : NO_SEATS}
                inbox={inbox}
                now={now}
                openThreadId={openThreadId}
              />
            )}
          </Resolved>
        )}
        {children}
      </main>
    </>
  );
}

/**
 * The middle pane with no conversation open.
 *
 * Two different nothings, and the second is the one that matters. A principal
 * the record holds no seat row for is `unaddressable`: it can neither receive a
 * message nor address one, so this surface is not quiet — it has no address at
 * all. That is a state one operator action clears, so the pane names the
 * command that clears it rather than leaving the reader with a word from the
 * projection's vocabulary.
 */
function Nowhere({
  said,
  fix = null,
}: {
  readonly said: string;
  /** The command that changes this state, when one does. */
  readonly fix?: string | null;
}): ReactElement {
  return (
    <div className="cw-main">
      <div className="cw-nil">
        <NothingGlyph />
        <span>{said}</span>
        {fix === null ? null : (
          <code
            className="mono"
            title="a seat credential mints a principal with a seat row, which is what an address is"
          >
            {fix}
          </code>
        )}
      </div>
    </div>
  );
}

async function OpenThread({
  thread,
  tab,
}: {
  readonly thread: InboxThread;
  readonly tab: WorkTab;
}): Promise<ReactElement> {
  const send = sendMessageAction.bind(null, thread.threadId);
  const promote = promoteThreadAction.bind(null, thread.threadId);
  const [correspondent, picker, board, delivery] = await Promise.all([
    recordAdapter.inboxCorrespondent(thread.threadId),
    recordAdapter.inboxPromotionPicker(),
    thread.promotedTicketId === null
      ? Promise.resolve(null)
      : recordAdapter.board(defaultProjectKey()),
    // the record refuses a read-state read on a thread holding no message, so
    // an empty conversation is an answered absence rather than a failed read
    thread.messages.length === 0
      ? Promise.resolve(EMPTY_DELIVERY)
      : recordAdapter.inboxDelivery(thread.threadId),
  ]);
  const settled = thread.messages.map((message) => message.messageId);
  const card =
    board === null || thread.promotedTicketId === null
      ? null
      : cardFor(board, thread.promotedTicketId);
  return (
    <Resolved
      brief
      frame={(declared) => (
        <div className="cw-main">
          <ThreadHead thread={thread} />
          <Transcript delivery={delivery} messages={thread.messages} self={null} />
          {declared}
        </div>
      )}
      reading={correspondent}
      subject="the seats this conversation is between"
    >
      {(value) => (
        <>
          <div className="cw-main">
            <ThreadHead thread={thread} />
            <Transcript delivery={delivery} messages={thread.messages} self={value.sender} />
            <ChatComposer action={send} correspondent={value} settled={settled} />
          </div>
          <WorkPanel
            card={card}
            promote={
              <LinkTicket action={promote} choices={picker.choices} notice={picker.notice} />
            }
            tab={tab}
            threadId={thread.threadId}
          >
            <SessionPane subject={value.recipient} />
          </WorkPanel>
        </>
      )}
    </Resolved>
  );
}

/** The thread read, unwrapped through the one boundary allowed to unwrap it. */
async function OpenThreadFrame({
  threadId,
  tab,
}: {
  readonly threadId: string;
  readonly tab: WorkTab;
}): Promise<ReactNode> {
  const thread = await recordAdapter.inboxThread(threadId);
  return (
    <Resolved
      frame={(declared) => <div className="cw-main">{declared}</div>}
      reading={thread}
      subject="this conversation"
    >
      {(value) => <OpenThread tab={tab} thread={value} />}
    </Resolved>
  );
}

function Middle({
  projection,
  composing,
  threadId,
  tab,
}: {
  readonly projection: InboxProjection;
  readonly composing: boolean;
  readonly threadId: string | null;
  readonly tab: WorkTab;
}): ReactNode {
  if (composing) {
    return <ComposeSlot />;
  }
  if (threadId !== null) {
    return <OpenThreadFrame tab={tab} threadId={threadId} />;
  }
  if (projection.threads.length > 0) {
    return <Nowhere said="pick a conversation" />;
  }
  if (projection.recipient === UNADDRESSABLE) {
    return <Nowhere fix={SEAT_COMMAND} said="this server holds no seat, so it has no address" />;
  }
  return <Nowhere said={`no conversation on record for ${projection.recipient}`} />;
}

/** The compose pane, which needs the correspondents read of its own. */
async function ComposeSlot(): Promise<ReactNode> {
  const correspondents = await recordAdapter.inboxCorrespondents();
  return (
    <Resolved
      frame={(declared) => <div className="cw-main">{declared}</div>}
      reading={correspondents}
      subject="the seats you can write to"
    >
      {(value) => <NewThread action={composeThreadAction} correspondents={value} />}
    </Resolved>
  );
}

export default async function InboxPage({
  searchParams,
}: {
  readonly searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<ReactNode> {
  const params = await searchParams;
  const threadId = readParam(params, "thread");
  const composing = readParam(params, "compose") !== null;
  const tab = tabOf(readParam(params, "pane"));
  const detail = threadId !== null || composing;
  const now = Date.now();
  const [inbox, correspondents] = await Promise.all([
    recordAdapter.inbox(),
    recordAdapter.inboxCorrespondents(),
  ]);
  return (
    <Resolved
      frame={(declared) => (
        <Workspace
          correspondents={correspondents}
          detail={detail}
          inbox={null}
          now={now}
          openThreadId={threadId}
        >
          <div className="cw-main">{declared}</div>
        </Workspace>
      )}
      reading={inbox}
    >
      {(projection) => (
        <Workspace
          correspondents={correspondents}
          detail={detail}
          inbox={projection}
          now={now}
          openThreadId={threadId}
        >
          <Middle composing={composing} projection={projection} tab={tab} threadId={threadId} />
        </Workspace>
      )}
    </Resolved>
  );
}
