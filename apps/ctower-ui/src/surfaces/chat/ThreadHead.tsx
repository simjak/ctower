import Link from "next/link";
import type { ReactElement } from "react";
import { shortId } from "@/read/elapsed";
import { DeliveryLegend } from "./Delivery";
import { TicketGlyph } from "./glyphs";
import type { InboxThread } from "@/read/interface";

/**
 * The head of the open conversation: who it is between, and where it is.
 *
 * The rejected screen spent a whole panel and a sentence on this. It is a
 * breadcrumb now — the participants, the thread's own identity as a mono chip,
 * and the ticket chip when the record links one — because a reader does not
 * need to be told that a thread has participants.
 *
 * It does *not* carry the instance any more. Provenance was drawn three times on
 * one screen — the frame's top bar, the conversation column's foot, and here —
 * and the third copy was what pushed this row into two lines at desk width and
 * three on a phone. D9's rule for a small closed vocabulary applies to a fact as
 * much as to a mark: it is drawn once. The column foot keeps the full origin,
 * posture and read stamp, which is the copy a capture is judged by.
 *
 * It carries the delivery legend, once, where the approved chat surface
 * puts it: three dot groups teaching the marks under every message below. The
 * legend is drawn only when there are messages to mark, so an empty
 * conversation does not explain a vocabulary nothing on screen is using.
 */
export function ThreadHead({ thread }: { readonly thread: InboxThread }): ReactElement {
  return (
    <div className="cw-head">
      <h2>{thread.participants.join(" · ")}</h2>
      <span className="cw-art" title={`thread ${thread.threadId}`}>
        {shortId(thread.threadId)}
      </span>
      {thread.promotedTicketId === null ? null : (
        <Link
          className="cw-art"
          href={`/ticket/${encodeURIComponent(thread.promotedTicketId)}`}
          title="the ticket this conversation was promoted to"
        >
          <TicketGlyph />
          {shortId(thread.promotedTicketId)}
        </Link>
      )}
      <span className="grow" />
      {thread.messages.length === 0 ? null : <DeliveryLegend />}
    </div>
  );
}
