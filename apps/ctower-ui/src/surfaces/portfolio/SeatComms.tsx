import Link from "next/link";
import type { ReactElement } from "react";
import { KnownAbsence, NoSourceYet, NotReached } from "@/frame/Declared";
import { NO_THREADS_HERE } from "@/read/futureSources";
import { shortId, stampText } from "@/read/elapsed";
import { Count } from "@/surfaces/Count";
import type { PortfolioComms, PortfolioThread, ThreadLink } from "@/read/interface";
import type { Known } from "@/read/sources/maybe";

/**
 * The mail half of the sweep: what the seats have said that nobody has read.
 *
 * The inbox projection is **recipient-scoped** — it answers for the principal
 * this surface reads with, not for the fleet — so this panel names that
 * principal rather than implying a fleet-wide count.
 *
 * The distinction the panel exists to keep is `addressable`. A principal with
 * no row in the project-seat registry is named `unaddressable` by the
 * projection: no thread can be addressed to it at all. Rendering that as
 * *0 unread* would tell the director the seats are quiet, when the truth is
 * that this reader is not a seat — the opposite claim. So the two are drawn as
 * two different things, and the second says which it is in words.
 *
 * A thread is attributed to a project only where a board card in that project
 * names it. Mail on threads no card links is counted apart, so the per-project
 * numbers and the unlinked number add up to the projection's own total instead
 * of being spread across projects the record never linked.
 *
 * That attribution is only as complete as the boards that answered, and the row
 * says so. A board that did not answer had its cards unread, and any of them
 * could name the thread in front of you — so *no answered board names it* is
 * printed as a link this page does not know, never as mail linked to nothing.
 */

/** Which projects a thread belongs to, or that this read cannot tell. */
function Linked({ link }: { readonly link: ThreadLink }): ReactElement {
  switch (link.known) {
    case "linked":
      return (
        <>
          {link.projects.map((project) => (
            <span className="chip" key={project}>
              {project}
            </span>
          ))}
        </>
      );
    case "unlinked":
      return <span>linked to no project</span>;
    case "unknown":
      return (
        <NotReached
          label={`link unknown · ${link.unreached.join(", ")} not reached`}
          detail={`no board that answered names this thread, and ${link.unreached.join(", ")} did not answer — a card there could name it, so this is not mail the record links to no project`}
        />
      );
  }
}

function ThreadRow({ thread }: { readonly thread: PortfolioThread }): ReactElement {
  const unread = thread.unreadCount > 0;
  return (
    <Link
      className={unread ? "msg unread" : "msg"}
      href={`/inbox?thread=${encodeURIComponent(thread.threadId)}`}
    >
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
        <Linked link={thread.link} />
        {thread.promotedTicketId === null ? null : <span>ticket linked</span>}
        <span className="mono">thread {shortId(thread.threadId)}</span>
      </div>
    </Link>
  );
}

/**
 * The `.how` slot is one masked line by design, so only a short note belongs in
 * it. The first render of this panel put the whole cannot-be-addressed sentence
 * there and the vendored fade cut it off mid-word — the one sentence on the page
 * that stops a zero being misread, truncated. It is a paragraph now.
 */
function Addressed({ comms }: { readonly comms: PortfolioComms }): ReactElement {
  return (
    <>
      <div className="addr" style={{ margin: "0 16px 0" }}>
        <span className="k">Addressed to</span>
        <span className="name">{comms.recipient}</span>
        <span className="how">
          recipient-scoped · this principal&rsquo;s mail, not the fleet&rsquo;s
        </span>
      </div>
      {comms.unaddressableWhy === null ? null : (
        <div className="body" style={{ paddingBottom: 0 }}>
          <p>{comms.unaddressableWhy}</p>
        </div>
      )}
    </>
  );
}

export function SeatComms({ comms }: { readonly comms: Known<PortfolioComms> }): ReactElement {
  if (comms.known !== "value") {
    return (
      <div className="body">
        <p>
          <KnownAbsence value={comms} />
        </p>
      </div>
    );
  }
  const value = comms.value;
  return (
    <div style={{ paddingTop: "12px" }}>
      <Addressed comms={value} />
      {/* an address that does not exist has already been answered above; adding
          "the record holds no thread for this principal" under it would say the
          record was consulted about an inbox that cannot exist */}
      {value.threads.length > 0 ? (
        <div>
          {value.threads.map((thread) => (
            <ThreadRow key={thread.threadId} thread={thread} />
          ))}
        </div>
      ) : value.addressable ? (
        <NoSourceYet brief source={NO_THREADS_HERE} />
      ) : null}
    </div>
  );
}
