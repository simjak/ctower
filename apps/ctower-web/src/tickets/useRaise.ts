import { useCallback, useState } from "react";
import type { Priority, TicketCommandResult } from "@ctower/client";
import { ask, commands, resendable } from "../api/client";
import type { Answer } from "../api/client";
import { commandKeyFor } from "../api/commandKey";

/**
 * Raising a ticket, and the one field the operator should not have to type.
 *
 * `createTicket` resolves the ticket's project from the custodian Commander's
 * own project seat, and refuses when the `project_key` on the command
 * disagrees with it. So the project is sent — the operator said which board
 * they are on and the record is the one that checks it — and the custodian is
 * asked for, because no operation in the authored contract enumerates
 * principals. The custodians already on this board are offered as suggestions,
 * which is a recorded fact rather than a guess.
 */
export interface Draft {
  readonly title: string;
  readonly priority: Priority;
  readonly sourceKind: string;
  readonly sourceRef: string;
  readonly custodian: string;
}

export const BLANK: Draft = {
  title: "",
  priority: "P1",
  sourceKind: "github-issue",
  sourceRef: "",
  custodian: "",
};

export interface Raise {
  readonly draft: Draft;
  readonly setDraft: (draft: Draft) => void;
  readonly armed: boolean;
  readonly sent: Answer<TicketCommandResult> | null;
  readonly send: () => void;
  readonly retry: (() => void) | null;
}

export function useRaise(projectKey: string): Raise {
  const [draft, setDraftState] = useState<Draft>(BLANK);
  const [sent, setSent] = useState<Answer<TicketCommandResult> | null>(null);

  const send = useCallback((): void => {
    setSent({ kind: "asking" });
    void (async (): Promise<void> => {
      setSent(await raised(projectKey, draft));
    })();
  }, [draft, projectKey]);

  const setDraft = useCallback((next: Draft): void => {
    setDraftState(next);
    setSent(null);
  }, []);

  return {
    draft,
    setDraft,
    armed: filled(draft),
    sent,
    send,
    retry: sent !== null && resendable(sent) ? send : null,
  };
}

function filled(draft: Draft): boolean {
  return (
    draft.title.trim() !== "" &&
    draft.sourceKind.trim() !== "" &&
    draft.sourceRef.trim() !== "" &&
    draft.custodian.trim() !== ""
  );
}

/**
 * The command, under a key derived from the act. Raising the same title from
 * the same source for the same custodian twice is one ticket, and a retry
 * after an answer nobody saw cannot become a second one.
 */
async function raised(projectKey: string, draft: Draft): Promise<Answer<TicketCommandResult>> {
  const source = { kind: draft.sourceKind.trim(), ref: draft.sourceRef.trim() };
  return ask(() =>
    commands.createTicket({
      IdempotencyKey: commandKeyFor(
        `raise:${projectKey}:${draft.custodian.trim()}:${source.kind}:${source.ref}:${draft.title.trim()}`
      ),
      body: {
        title: draft.title.trim(),
        priority: draft.priority,
        project_key: projectKey,
        source,
        initial_custodian_id: draft.custodian.trim(),
      },
    })
  );
}
