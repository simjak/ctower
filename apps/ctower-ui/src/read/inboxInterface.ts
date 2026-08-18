import type { InboxPromotionTicketChoice } from "@/mutate/types";

/**
 * The durable inbox, as the record projects it.
 *
 * This family moved out of `interface.ts` when the delivery models joined it:
 * the inbox is one cohesive subject — threads, their messages, who they are
 * between, and how far each message got — and the chat workspace is the only
 * screen that reads any of it. `interface.ts` re-exports the whole family, so
 * every existing import keeps working and `RecordAdapter` still declares these
 * reads beside the rest.
 */

/** One recipient-scoped row from the inbox threads projection. */
export interface InboxThreadSummary {
  readonly threadId: string;
  readonly otherAgent: string;
  readonly lastMessagePreview: string;
  readonly lastMessageAt: string;
  readonly unreadCount: number;
  /** The immutable ticket link, when this thread was promoted. */
  readonly promotedTicketId: string | null;
}

/** One ordered, durable message returned when the thread is opened. */
export interface InboxThreadMessage {
  readonly messageId: string;
  readonly position: number;
  readonly from: string;
  readonly to: string;
  readonly text: string;
  readonly sentAt: string;
}

/**
 * How far one message got: the record's own append-only delivery truth.
 *
 * `sent` means the record accepted it. `delivered` means the recipient's side
 * accepted it. `read` means the recipient opened the thread. The three are
 * recorded facts with their own event ids, not a guess from a read cursor, and
 * the two timestamps are null until the event that sets them is appended — so a
 * message that has not been read carries `readAt: null` rather than a time this
 * surface invented.
 */
export interface InboxMessageDelivery {
  readonly messageId: string;
  readonly position: number;
  readonly recipient: string;
  readonly severity: "P0" | "P1" | "info";
  readonly state: "sent" | "delivered" | "read";
  readonly deliveredAt: string | null;
  readonly readAt: string | null;
}

/**
 * A thread's delivery truth, keyed by the message it belongs to.
 *
 * This is a *second* read and can fail on its own, which is why it is kept
 * apart from `InboxThread` rather than folded into its messages: a transcript
 * whose delivery read did not answer must draw no marks at all and say so,
 * never draw every message as merely `sent`.
 */
export type InboxDelivery = ReadonlyMap<string, InboxMessageDelivery>;

/** The full thread projection. Reading it advances only the recipient's read cursor. */
export interface InboxThread {
  readonly threadId: string;
  readonly participants: readonly string[];
  readonly messages: readonly InboxThreadMessage[];
  readonly readThroughPosition: number;
  /** The immutable ticket link, when this thread was promoted. */
  readonly promotedTicketId: string | null;
}

/** The authenticated principal's inbox projection. */
export interface InboxProjection {
  readonly recipient: string;
  readonly threads: readonly InboxThreadSummary[];
  readonly totalUnread: number;
  readonly unreadOnly: boolean;
}

/**
 * Who one thread is between, as the recipient-scoped projection itself names
 * them — never as this surface infers them.
 *
 * A message needs an address, and the address is an identity. So it is read
 * back from the server rather than assembled here or accepted from a form: the
 * projection says which seat the authenticated principal holds and which seat
 * is on the other end of this thread, and the send path asks for that answer
 * again at submit time rather than trusting one a browser round-tripped.
 */
export interface InboxCorrespondent {
  /** The seat this surface's authenticated principal holds. */
  readonly sender: string;
  /** The other participant: where a message on this thread is addressed. */
  readonly recipient: string;
}

/** One registered seat a new thread can be addressed to. */
export interface InboxCorrespondentChoice {
  readonly seatKey: string;
  readonly projectKey: string;
}

/**
 * Who this principal may open a new thread to, as the record itself lists them.
 *
 * A compose control has nobody to read a recipient back from — the thread it
 * addresses does not exist yet — so the address has to be chosen. What keeps it
 * from being a claimed identity is that the choices are the record's own
 * registered seats: the same closed world the send command resolves against, so
 * this picker can offer no address the record would not accept, and a seat it
 * does not list is refused server-side rather than created.
 */
export interface InboxCorrespondents {
  /** The seat this surface's authenticated principal holds. */
  readonly sender: string;
  readonly choices: readonly InboxCorrespondentChoice[];
}

/** Ticket choices the current principal's Board read made available for Inbox linking. */
export interface InboxPromotionPicker {
  readonly choices: readonly InboxPromotionTicketChoice[];
  /** A failed Board read never becomes an empty ticket list without this explanation. */
  readonly notice: string | null;
}
