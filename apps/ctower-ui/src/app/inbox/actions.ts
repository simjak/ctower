"use server";

import { promoteInboxThread } from "@/mutate/inboxPromotion";
import type { InboxPromotionState } from "@/mutate/types";

/** Server action: the browser submits intent, while this server holds the bearer. */
export async function promoteThreadAction(
  threadId: string,
  _previous: InboxPromotionState,
  formData: FormData
): Promise<InboxPromotionState> {
  const selected = formData.get("ticket_id");
  const ticketId = typeof selected === "string" && selected !== "" ? selected : null;
  return await promoteInboxThread(threadId, ticketId);
}
