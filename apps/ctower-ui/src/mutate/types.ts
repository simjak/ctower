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
 */
export type InboxSendState =
  | { readonly kind: "idle" }
  | { readonly kind: "sent"; readonly message: InboxAcceptedMessage }
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
