import Link from "next/link";
import type { ReactElement } from "react";
import { recordAdapter } from "@/read/adapter";
import { elapsedSince, stampText } from "@/read/elapsed";
import { Count } from "@/surfaces/Count";
import { NothingGlyph, PlusGlyph } from "./glyphs";
import { PLANE_HINT, PLANE_WHY } from "./plane";
import type { InboxProjection, InboxThreadSummary } from "@/read/interface";

/**
 * The conversations column.
 *
 * Every fact the old screen spelled out is still here and none of it is a
 * sentence: unread is the accent bar down the left edge and the pill on the
 * right, recency is the age at the top right, the subject is the projection's
 * own last-message preview, and the open conversation is the row with the ink
 * bar. A reader learns the list by looking at it.
 *
 * `New` is the compose control, and it is a real one — it opens the seats the
 * record itself lists. Where the record lists none it is `aria-disabled` with
 * the reason on its `title`, because an affordance that cannot be honoured must
 * look like it cannot be honoured.
 */

function ageOf(at: string, now: number): string {
  return elapsedSince(at, now) ?? "—";
}

function ThreadRow({
  thread,
  open,
  now,
}: {
  readonly thread: InboxThreadSummary;
  readonly open: boolean;
  readonly now: number;
}): ReactElement {
  const unread = thread.unreadCount > 0;
  const marks = [open ? "cw-row on" : "cw-row", unread ? "unread" : ""].join(" ").trim();
  return (
    <Link
      aria-current={open ? "page" : undefined}
      className={marks}
      href={`/inbox?thread=${encodeURIComponent(thread.threadId)}`}
      title={`${thread.unreadCount.toString()} unread of the messages this conversation holds`}
    >
      <span className="bar" />
      <span className="who">{thread.otherAgent}</span>
      <span className="age">{ageOf(thread.lastMessageAt, now)}</span>
      <span className="last">{thread.lastMessagePreview}</span>
      {unread ? (
        <span className="tally">
          <Count
            detail={`${thread.unreadCount.toString()} unread of the messages this conversation holds`}
            unit="unread"
            value={thread.unreadCount}
          />
        </span>
      ) : (
        <span />
      )}
    </Link>
  );
}

export function ThreadList({
  inbox,
  openThreadId,
  canCompose,
  composeReason,
  now,
}: {
  readonly inbox: InboxProjection;
  readonly openThreadId: string | null;
  /** Whether the record listed anyone this principal may open a thread to. */
  readonly canCompose: boolean;
  /** Why not, when it listed nobody — carried on the control, not on the page. */
  readonly composeReason: string;
  readonly now: number;
}): ReactElement {
  return (
    <aside className="cw-list">
      <div className="cw-head">
        <h2>Conversations</h2>
        {inbox.totalUnread === 0 ? null : (
          <Count
            detail={`${inbox.totalUnread.toString()} unread across ${inbox.threads.length.toString()} conversations`}
            unit="unread"
            value={inbox.totalUnread}
          />
        )}
        <span className="grow" />
        {canCompose ? (
          <Link
            aria-label="Start a conversation"
            className="cw-act"
            href="/inbox?compose=1"
            title="Start a conversation"
          >
            <PlusGlyph />
          </Link>
        ) : (
          <span aria-disabled className="cw-act" title={composeReason}>
            <PlusGlyph />
          </span>
        )}
      </div>
      {/* the one thing about this surface that catches a reader out, in the one
          line D9 allows for it: the inbox is transport, and neither send nor
          notify evaluates a project grant. The picker files its seats under
          their projects, which is the same fact drawn rather than said. */}
      <p className="cw-hint" title={PLANE_WHY}>
        {PLANE_HINT}
      </p>
      {inbox.threads.length === 0 ? (
        <div className="cw-nil">
          <NothingGlyph />
          <span>no conversation on record</span>
        </div>
      ) : (
        <div className="cw-rows">
          {inbox.threads.map((thread) => (
            <ThreadRow
              key={thread.threadId}
              now={now}
              open={thread.threadId === openThreadId}
              thread={thread}
            />
          ))}
        </div>
      )}
      <div className="foot cw-foot">
        <span>ctower · {recordAdapter.instance.label} instance</span>
        <span>{recordAdapter.instance.baseUrl}</span>
        <span>{recordAdapter.instance.posture}</span>
        <span>rendered {stampText(new Date().toISOString())}</span>
      </div>
    </aside>
  );
}
