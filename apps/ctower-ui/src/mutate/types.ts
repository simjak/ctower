/** Client-safe shape of the one Inbox promotion result this UI can render. */
export type InboxPromotionState =
  | { readonly kind: "idle" }
  | {
      readonly kind: "promoted";
      readonly ticketId: string;
      readonly outcome: "ticket_created" | "ticket_linked";
    }
  | { readonly kind: "refused"; readonly message: string };

/**
 * Client-safe shape of the one Inbox send result this UI can render.
 *
 * The accepted message is the server's whole answer, not the form's request:
 * the send path claims no sender and the browser names no recipient, so the
 * seats, the position and the timestamp shown back are the ones the API
 * actually recorded. It is carried in full because the thread list cannot show
 * the message yet — that list is a projection folded from events after the
 * command commits — and a sender who has to reload to see their own message is
 * not chatting with anyone.
 *
 * `pending` is the state the record itself names. A `202` answer carries the
 * same message identity, position and timestamp an accepted one does, and means
 * the opposite thing: the durable acknowledgement acceptance requires has not
 * committed, so nothing here is a message anyone has promised to keep. It is a
 * state of its own rather than a flag on `sent`, because every surface that can
 * render a send has to choose which of the two it is looking at.
 */
export type InboxSendState =
  | { readonly kind: "idle" }
  | { readonly kind: "sent"; readonly message: InboxAcceptedMessage }
  | {
      readonly kind: "pending";
      /** Why nothing was drawn: the server has not confirmed this message. */
      readonly message: string;
      /** What the operator typed, still theirs until the record takes it. */
      readonly text: string;
      /** The identity every retry of this same message sends again. */
      readonly commandId: string;
    }
  | {
      readonly kind: "refused";
      readonly message: string;
      /** What the operator typed, so a refusal never costs them their words. */
      readonly text: string;
    };

/** One message exactly as the send command answered with it. */
export interface InboxAcceptedMessage {
  readonly messageId: string;
  readonly position: number;
  readonly from: string;
  readonly to: string;
  readonly text: string;
  readonly sentAt: string;
}

/** A ticket the server-side Board read made available for explicit linking. */
export interface InboxPromotionTicketChoice {
  readonly ticketId: string;
  readonly projectKey: string;
  readonly title: string;
}
