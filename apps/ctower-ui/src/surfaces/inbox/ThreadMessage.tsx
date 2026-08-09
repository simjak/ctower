import type { ReactElement } from "react";
import { stampText } from "@/read/elapsed";
import type { InboxThreadMessage } from "@/read/interface";

/**
 * One message row, written once.
 *
 * The thread list and the send box both render a message, and the send box's
 * is the newer of the two: the projection that answers the list is folded from
 * events after the command commits, so a message the record has already
 * accepted is briefly absent from it. Both rows come from here so the newer one
 * cannot drift into a different shape, and `note` is the only difference —
 * the word that says this row is ahead of the list, not a second kind of thing.
 */
export function ThreadMessage({
  message,
  note = null,
}: {
  readonly message: InboxThreadMessage;
  /** A short marker for a row the thread projection has not folded yet. */
  readonly note?: string | null;
}): ReactElement {
  return (
    <div className="msg">
      <span className="dot" />
      <div className="subj">{message.text}</div>
      <div className="when">{stampText(message.sentAt)}</div>
      <div className="meta">
        <span>from {message.from}</span>
        <span>to {message.to}</span>
        <span>message {message.position.toString()}</span>
        {note === null ? null : <span className="verdict v-flight">{note}</span>}
      </div>
    </div>
  );
}
