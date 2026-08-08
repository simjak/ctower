/** Client-safe shape of the one Inbox promotion result this UI can render. */
export type InboxPromotionState =
  | { readonly kind: "idle" }
  | {
      readonly kind: "promoted";
      readonly ticketId: string;
      readonly outcome: "ticket_created" | "ticket_linked";
    }
  | { readonly kind: "refused"; readonly message: string };

/** A ticket the server-side Board read made available for explicit linking. */
export interface InboxPromotionTicketChoice {
  readonly ticketId: string;
  readonly projectKey: string;
  readonly title: string;
}
