"use server";

import { revalidatePath } from "next/cache";
import { composeInboxThread } from "@/mutate/inboxCompose";
import { promoteInboxThread } from "@/mutate/inboxPromotion";
import { sendInboxMessage } from "@/mutate/inboxSend";
import type { InboxComposeState, InboxPromotionState, InboxSendState } from "@/mutate/types";

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
 * Server action: the browser submits message text, and the answer it last got.
 *
 * The thread is bound from the route, the recipient is resolved server-side,
 * and the sender is the bearer's own principal. An accepted message revalidates
 * this route so the thread re-renders with it in place — the reader never
 * reloads to see what they just sent, and never sees a message the record has
 * not answered with. Nothing is revalidated for an answer the record did not
 * accept: there is no new truth to re-read, and `previous` carries that send's
 * identity back so pressing the box again retries it rather than duplicating it.
 */
export async function sendMessageAction(
  threadId: string,
  previous: InboxSendState,
  formData: FormData
): Promise<InboxSendState> {
  const typed = formData.get("text");
  const state = await sendInboxMessage(threadId, typeof typed === "string" ? typed : "", previous);
  if (state.kind === "sent") {
    revalidatePath("/inbox");
  }
  return state;
}

/**
 * Server action: the browser submits a message and which listed seat it is for.
 *
 * The seat is a choice among the server's own answer, not an asserted identity:
 * it is checked back against that list before any command is made, and the API
 * resolves it again from the bearer this server holds. The thread is chosen by
 * nobody — the server derives one per seat pair — and the sender is never sent.
 * An accepted compose revalidates this route so the thread list re-renders with
 * the new conversation in it as soon as the projection folds it, while the
 * message itself is drawn from the command's own answer in the same document.
 * Nothing is revalidated for an answer the record did not accept: there is no
 * new truth to re-read, and `previous` carries that send's identity back so
 * pressing the box again retries it rather than starting a second conversation.
 */
export async function composeThreadAction(
  previous: InboxComposeState,
  formData: FormData
): Promise<InboxComposeState> {
  const seat = formData.get("to");
  const typed = formData.get("text");
  const state = await composeInboxThread(
    typeof seat === "string" ? seat : "",
    typeof typed === "string" ? typed : "",
    previous
  );
  if (state.kind === "started") {
    revalidatePath("/inbox");
  }
  return state;
}
