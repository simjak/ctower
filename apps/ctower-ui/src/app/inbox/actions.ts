"use server";

import { revalidatePath } from "next/cache";
import { promoteInboxThread } from "@/mutate/inboxPromotion";
import { sendInboxMessage } from "@/mutate/inboxSend";
import type { InboxPromotionState, InboxSendState } from "@/mutate/types";

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

/**
 * Server action: the browser submits message text, and only message text.
 *
 * The thread is bound from the route, the recipient is resolved server-side,
 * and the sender is the bearer's own principal. An accepted message revalidates
 * this route so the thread re-renders with it in place — the reader never
 * reloads to see what they just sent, and never sees a message the record has
 * not answered with.
 */
export async function sendMessageAction(
  threadId: string,
  _previous: InboxSendState,
  formData: FormData
): Promise<InboxSendState> {
  const typed = formData.get("text");
  const state = await sendInboxMessage(threadId, typeof typed === "string" ? typed : "");
  if (state.kind === "sent") {
    revalidatePath("/inbox");
  }
  return state;
}
