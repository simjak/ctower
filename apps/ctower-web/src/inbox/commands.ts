import { useCallback, useRef, useState } from "react";
import type {
  InboxAcknowledgeResult,
  InboxMessage,
  InboxSendRequest,
  InboxSendResult,
} from "@ctower/client";
import { ask, ASKING, commands } from "../api/client";
import type { Answer } from "../api/client";
import { uuid } from "../api/telemetry";

/**
 * The two things this page records, and the identity rule both obey.
 *
 * A command crossing this boundary may be retried only under the one key it was
 * first sent with, so a send holds its key for the life of the attempt chain and
 * drops it only once ctower has answered. That is what lets the screen offer
 * "send it again" after silence instead of telling the operator to reload and
 * guess: the same key cannot write twice.
 */

export type Severity = InboxSendRequest["severity"];

export interface Draft {
  /** The thread this answers, or nothing when it opens one. */
  readonly threadId: string | null;
  readonly to: string;
  readonly projectKey: string;
  readonly severity: Severity;
  readonly text: string;
}

export interface Send {
  /** Nothing has been sent yet, or what came back of the last one. */
  readonly outcome: Answer<InboxSendResult> | null;
  readonly send: (draft: Draft) => void;
  /** The last draft, held only so silence can be answered by the same command. */
  readonly again: (() => void) | null;
  readonly clear: () => void;
}

export function useSend(onRecorded: () => void): Send {
  const [outcome, setOutcome] = useState<Answer<InboxSendResult> | null>(null);
  const key = useRef<string | null>(null);
  const last = useRef<Draft | null>(null);

  const send = useCallback(
    (draft: Draft): void => {
      last.current = draft;
      key.current ??= uuid();
      const idempotencyKey = key.current;
      setOutcome(ASKING);
      const run = async (): Promise<void> => {
        const answer = await ask(() =>
          commands.sendInboxMessage({ IdempotencyKey: idempotencyKey, body: bodyOf(draft) })
        );
        setOutcome(answer);
        if (answer.kind === "answered") {
          // ctower has the message. The next one is a different act and gets a
          // different identity.
          key.current = null;
          onRecorded();
        }
      };
      void run();
    },
    [onRecorded]
  );

  const clear = useCallback((): void => {
    setOutcome(null);
  }, []);

  const heldDraft = last.current;
  const retryable = outcome !== null && outcome.kind === "unreachable" && heldDraft !== null;

  return {
    outcome,
    send,
    again: retryable
      ? (): void => {
          send(heldDraft);
        }
      : null,
    clear,
  };
}

function bodyOf(draft: Draft): InboxSendRequest {
  const opened = {
    project_key: draft.projectKey,
    severity: draft.severity,
    to: draft.to,
    text: draft.text,
  };
  return draft.threadId === null ? opened : { ...opened, thread_id: draft.threadId };
}

export interface Acknowledged {
  readonly count: number;
}

export interface MarkRead {
  readonly outcome: Answer<Acknowledged> | null;
  readonly mark: (unread: readonly InboxMessage[]) => void;
}

/**
 * Reading is a recorded fact, and it is recorded one message at a time: the
 * contract acknowledges a message, never a thread, and the thread's read
 * position is derived from the oldest message still unread. So marking a thread
 * read is exactly the acknowledgements it is made of, sent in order, and the
 * first one ctower does not accept stops the run and is what the screen shows.
 */
export function useMarkRead(onRecorded: () => void): MarkRead {
  const [outcome, setOutcome] = useState<Answer<Acknowledged> | null>(null);

  const mark = useCallback(
    (unread: readonly InboxMessage[]): void => {
      setOutcome(ASKING);
      const run = async (): Promise<void> => {
        const answer = await acknowledge(unread);
        setOutcome(answer);
        onRecorded();
      };
      void run();
    },
    [onRecorded]
  );

  return { outcome, mark };
}

async function acknowledge(unread: readonly InboxMessage[]): Promise<Answer<Acknowledged>> {
  let count = 0;
  for (const message of unread) {
    const answer: Answer<InboxAcknowledgeResult> = await ask(() =>
      commands.acknowledgeInboxMessage({
        messageId: message.message_id,
        IdempotencyKey: uuid(),
        body: { state: "read" },
      })
    );
    if (answer.kind !== "answered") {
      return answer;
    }
    count += 1;
  }
  return { kind: "answered", value: { count } };
}
