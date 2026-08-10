"use server";

import {
  confirmConsoleCommand,
  dispatchConsoleInput,
  mintConsoleTypeGrant,
} from "@/mutate/consoleTyping";
import type { ConsoleTypingState } from "@/mutate/types";
import { REFUSAL } from "@/surfaces/console/typing";

/**
 * Server action: the browser submits one intent and the answer it last got.
 *
 * The session is bound from the route, never from the payload — a browser that
 * could name its own target would be naming a tmux pane, and the console fence
 * refuses browser-supplied targets by design. The bearer stays on this server.
 *
 * `previous` is where the confirmation and the grant come back from. Neither is
 * authority: the server holds the canonical object behind the digest and the
 * grant behind its identity, and re-presenting either is exactly what the
 * single-use check and the compare-and-set are for. What `previous` buys is
 * that this surface never has to hold two sources of truth for one ceremony.
 *
 * Nothing is revalidated. Every answer here is about a command, not about a
 * projection this route reads, and a grant that mints is not new page truth.
 */
export async function consoleTypingAction(
  sessionRef: string,
  previous: ConsoleTypingState,
  formData: FormData
): Promise<ConsoleTypingState> {
  const intent = formData.get("intent");
  const typed = formData.get("text");
  const text = typeof typed === "string" ? typed : "";

  if (intent === "cancel") {
    return { kind: "idle" };
  }
  if (intent === "open") {
    return { kind: "opened" };
  }
  if (intent === "confirm") {
    return await confirmConsoleCommand(sessionRef, "paste_text", text);
  }
  if (intent === "confirm_submit") {
    return await confirmConsoleCommand(sessionRef, "submit", "");
  }
  if (intent === "mint") {
    return previous.kind === "confirmed"
      ? await mintConsoleTypeGrant(sessionRef, previous.ceremony)
      : { kind: "refused", message: REFUSAL.unreadable, text };
  }
  if (intent === "present") {
    return previous.kind === "granted"
      ? await dispatchConsoleInput(sessionRef, previous.grant, text)
      : { kind: "refused", message: REFUSAL.unreadable, text };
  }
  return { kind: "refused", message: REFUSAL.unreadable, text };
}
