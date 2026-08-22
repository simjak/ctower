import { useCallback, useState } from "react";
import type { SeatCredentialReceipt } from "@ctower/client";
import { ask, ASKING, commands } from "../../api/client";
import type { Answer } from "../../api/client";
import { canonicalDigest } from "../../mint/digest";
import { commandKeyFor } from "../../wizard/apply/commandKey";
import type { Minted } from "./roster";

/**
 * Taking a crew's address away.
 *
 * `revokeSeatCredential` asks for a reason and records it on the event, so the
 * reason is a field and not a formality: it is the only thing that will explain
 * this to whoever reads the record later. The confirmation is the operator's
 * own, because ctower refuses this from anyone else.
 *
 * The revocation receipt names the same credential and supersedes the issuance,
 * so it goes into the same ledger and the roster row changes state rather than
 * gaining a second address.
 */
export interface RevokeAct {
  readonly open: Minted | null;
  readonly reason: string;
  readonly setReason: (reason: string) => void;
  readonly armed: boolean;
  readonly setArmed: (armed: boolean) => void;
  readonly start: (minted: Minted) => void;
  readonly cancel: () => void;
  readonly send: () => void;
  readonly outcome: Answer<SeatCredentialReceipt> | null;
}

const MAX_REASON = 500;

export function useRevokeAct(record: (minted: Minted) => void): RevokeAct {
  const [open, setOpen] = useState<Minted | null>(null);
  const [reason, setReason] = useState("");
  const [armed, setArmed] = useState(false);
  const [outcome, setOutcome] = useState<Answer<SeatCredentialReceipt> | null>(null);

  const start = useCallback((minted: Minted): void => {
    setOpen(minted);
    setReason("");
    setArmed(false);
    setOutcome(null);
  }, []);

  const cancel = useCallback((): void => {
    setOpen(null);
    setReason("");
    setArmed(false);
    setOutcome(null);
  }, []);

  const send = useCallback((): void => {
    if (open === null || !sayable(reason)) {
      return;
    }
    const credentialId = open.receipt.credential_id;
    setOutcome(ASKING);
    void (async (): Promise<void> => {
      const answer = await ask(() =>
        commands.revokeSeatCredential({
          credentialId,
          IdempotencyKey: commandKeyFor(canonicalDigest({ credentialId, reason })),
          body: { reason },
        })
      );
      setOutcome(answer);
      if (answer.kind === "answered") {
        record({ subject: open.subject, receipt: answer.value });
      }
    })();
  }, [open, reason, record]);

  return { open, reason, setReason, armed, setArmed, start, cancel, send, outcome };
}

/** The contract's own bound on a reason, so an over-long one is caught here. */
export function sayable(reason: string): boolean {
  return reason.trim().length > 0 && reason.length <= MAX_REASON;
}
