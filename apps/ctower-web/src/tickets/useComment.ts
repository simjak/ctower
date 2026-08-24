import { useCallback, useState } from "react";
import type { TicketCommentResult } from "@ctower/client";
import { ask, commands, resendable } from "../api/client";
import type { Answer } from "../api/client";
import { commandKeyFor } from "../api/commandKey";

/**
 * Saying something on a ticket.
 *
 * One field, because the command carries one: `addTicketComment` takes a body
 * and nothing else. The note is the operator's own words and is sent verbatim.
 *
 * The idempotency key is derived from the ticket and the words, so a resend
 * after an answer nobody saw records the same note rather than a second copy of
 * it. Saying the same thing twice on purpose is a different act, and the key
 * only holds for as long as the composer holds those words.
 */
export interface Comment {
  readonly typed: string;
  readonly setTyped: (typed: string) => void;
  readonly armed: boolean;
  readonly sent: Answer<TicketCommentResult> | null;
  readonly send: () => void;
  readonly retry: (() => void) | null;
}

export function useComment(ticketId: string, onSaid: () => void): Comment {
  const [typed, setTypedState] = useState("");
  const [sent, setSent] = useState<Answer<TicketCommentResult> | null>(null);

  const send = useCallback((): void => {
    setSent({ kind: "asking" });
    void (async (): Promise<void> => {
      const answer = await ask(() =>
        commands.addTicketComment({
          ticketId,
          IdempotencyKey: commandKeyFor(`comment:${ticketId}:${typed.trim()}`),
          body: { body: typed.trim() },
        })
      );
      setSent(answer);
      if (answer.kind === "answered") {
        setTypedState("");
        onSaid();
      }
    })();
  }, [onSaid, ticketId, typed]);

  const setTyped = useCallback((next: string): void => {
    setTypedState(next);
    setSent(null);
  }, []);

  return {
    typed,
    setTyped,
    armed: typed.trim() !== "",
    sent,
    send,
    retry: sent !== null && resendable(sent) ? send : null,
  };
}
