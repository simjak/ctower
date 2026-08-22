import { useCallback, useState } from "react";
import type { WorkflowReceipt } from "@ctower/client";
import { ask, commands, resendable } from "../api/client";
import type { Answer } from "../api/client";
import { commandKeyFor } from "../api/commandKey";
import type { StandingWorkflow } from "./workflow";

/**
 * One stage move, and the four facts the record needs to accept it.
 *
 * Three of them are read, never typed: the workflow, the stage it stands at,
 * and the version that move must expect all come from the ticket's own last
 * recorded `workflow.changed`. The operator names only where it goes, because
 * no operation in the authored contract returns a workflow's stage graph and a
 * list of choices here would be a graph this console made up.
 *
 * The idempotency key is derived from the act — this ticket, this workflow,
 * this version, this destination — so a retry is the same command and cannot
 * move a ticket twice, while changing the destination is correctly a different
 * command.
 */
export interface Move {
  readonly destination: string;
  readonly setDestination: (destination: string) => void;
  /** Whether the destination names somewhere other than where it already is. */
  readonly armed: boolean;
  readonly sent: Answer<WorkflowReceipt> | null;
  readonly send: () => void;
  readonly retry: (() => void) | null;
}

export function useMove(ticketId: string, standing: StandingWorkflow, onMoved: () => void): Move {
  const [destination, setDestinationState] = useState("");
  const [sent, setSent] = useState<Answer<WorkflowReceipt> | null>(null);
  const wanted = destination.trim();
  const armed = wanted !== "" && wanted !== standing.stage && !standing.closed;

  const send = useCallback((): void => {
    setSent({ kind: "asking" });
    void (async (): Promise<void> => {
      const answer = await ask(() =>
        commands.transitionWorkflow({
          ticketId,
          IdempotencyKey: commandKeyFor(
            `move:${ticketId}:${standing.reference}:${String(standing.version)}:${wanted}`
          ),
          body: {
            workflow_ref: standing.reference,
            source_stage: standing.stage,
            destination_stage: wanted,
            expected_version: standing.version,
          },
        })
      );
      setSent(answer);
      // Only acceptance moved the ticket. `durability_pending` did not, so
      // nothing is re-read on it and the retry stays offered.
      if (answer.kind === "answered" && answer.value.durability_state === "accepted") {
        onMoved();
      }
    })();
  }, [onMoved, standing, ticketId, wanted]);

  const setDestination = useCallback((next: string): void => {
    setDestinationState(next);
    setSent(null);
  }, []);

  return {
    destination,
    setDestination,
    armed,
    sent,
    send,
    retry: sent !== null && resendable(sent) ? send : null,
  };
}
