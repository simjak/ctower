import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { stampText } from "@/read/elapsed";
import type { InboxThreadMessage } from "@/read/interface";

/**
 * One message row, written once.
 *
 * The thread list, the send box and the compose box all render a message, and
 * the two boxes' rows are the newer of them: the projection that answers the
 * list is folded from events after the command commits, so a message the
 * record has already accepted is briefly absent from it. Every row comes from
 * here so the newer ones cannot drift into a different shape, and `note` is
 * the word that says a row is ahead of the list, not a second kind of thing.
 *
 * `href` makes the row the way into the thread it belongs to, which is what a
 * `.msg` row already is everywhere else on this screen. A compose needs it: the
 * conversation it just started is somewhere the reader has not been yet, and a
 * separate link under an emptied form would be a second idiom for the one the
 * thread list already teaches.
 */
export function ThreadMessage({
  message,
  note = null,
  href = null,
}: {
  readonly message: InboxThreadMessage;
  /** A short marker for a row the thread projection has not folded yet. */
  readonly note?: string | null;
  /** Where this row leads, when it leads anywhere. */
  readonly href?: string | null;
}): ReactElement {
  const row: ReactNode = (
    <>
      <span className="dot" />
      <div className="subj">{message.text}</div>
      <div className="when">{stampText(message.sentAt)}</div>
      <div className="meta">
        <span>from {message.from}</span>
        <span>to {message.to}</span>
        <span>message {message.position.toString()}</span>
        {note === null ? null : <span className="verdict v-flight">{note}</span>}
      </div>
    </>
  );
  if (href === null) {
    return <div className="msg">{row}</div>;
  }
  return (
    <Link className="msg" href={href} title="Open this thread">
      {row}
    </Link>
  );
}
