import { useCallback, useState } from "react";
import type { Priority, TicketCommandResult } from "@ctower/client";
import { ask, commands, resendable } from "../api/client";
import type { Answer } from "../api/client";
import { commandKeyFor } from "../api/commandKey";

/**
 * Raising a ticket, and the three fields that is actually made of.
 *
 * The operator types one thing. Everything else on the command is either what
 * he chose with a word — which project, how urgent — or a fact the record
 * already holds and this console must not ask him for:
 *
 * - **who takes it** is omitted. `createTicket` assigns the calling principal
 *   when `initial_custodian_id` is absent (`ctower_api/interface.py`), so "Me"
 *   is the record's own answer rather than a box this console filled in. There
 *   is no read that enumerates principals, so any other name would be typed
 *   blind — which is exactly what the deleted form asked for.
 * - **where it came from** is this console. `source.kind` is a free string in
 *   the authored contract, so the truth fits: it was raised here. The old
 *   default said `github-issue` about a ticket no issue ever existed for.
 */
export interface Draft {
  readonly title: string;
  readonly priority: Priority;
  /** The project it is raised on — the switcher's answer, changeable in the pop-up. */
  readonly project: string;
}

/** What this console is, said the way the record's own `source` field takes it. */
const SOURCE = { kind: "ui", ref: "ctower-web/tickets" } as const;

export interface Raise {
  readonly draft: Draft;
  readonly setDraft: (draft: Draft) => void;
  readonly armed: boolean;
  readonly sent: Answer<TicketCommandResult> | null;
  readonly send: () => void;
  readonly retry: (() => void) | null;
}

export function useRaise(projectKey: string): Raise {
  const [draft, setDraftState] = useState<Draft>({
    title: "",
    priority: "P1",
    project: projectKey,
  });
  const [sent, setSent] = useState<Answer<TicketCommandResult> | null>(null);

  const send = useCallback((): void => {
    setSent({ kind: "asking" });
    void (async (): Promise<void> => {
      setSent(await raised(draft));
    })();
  }, [draft]);

  const setDraft = useCallback((next: Draft): void => {
    setDraftState(next);
    setSent(null);
  }, []);

  return {
    draft,
    setDraft,
    armed: draft.title.trim() !== "",
    sent,
    send,
    retry: sent !== null && resendable(sent) ? send : null,
  };
}

/**
 * The command, under a key derived from the act. Raising the same title at the
 * same urgency on the same project twice is one ticket, and a retry after an
 * answer nobody saw cannot become a second one.
 */
async function raised(draft: Draft): Promise<Answer<TicketCommandResult>> {
  return ask(() =>
    commands.createTicket({
      IdempotencyKey: commandKeyFor(
        `raise:${draft.project}:${draft.priority}:${draft.title.trim()}`
      ),
      body: {
        title: draft.title.trim(),
        priority: draft.priority,
        project_key: draft.project,
        source: SOURCE,
      },
    })
  );
}
