import { RotateCw } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import type { DurabilityState } from "@ctower/client";
import type { Answer } from "../api/client";
import { Button } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";

/**
 * What came back from a command, and the one thing it may not do: call a
 * pending write done. `durability_pending` is not acceptance, so it is not
 * drawn as one.
 *
 * Three of the four outcomes tell the operator that sending again is safe, so
 * sending again is a control here rather than an instruction to reload. It is
 * the same command under the same idempotency key — that is the whole reason
 * the promise can be made.
 */
export function Sent({
  sent,
  doing,
  nothingHappened,
  receipt,
  onRetry,
}: {
  readonly sent: Answer<{ readonly durability_state: DurabilityState }>;
  /** What is in flight, as a phrase: "Moving this ticket". */
  readonly doing: string;
  /** What a refusal leaves behind, in one sentence. */
  readonly nothingHappened: string;
  /** What to draw once ctower has answered. */
  readonly receipt: ReactNode;
  readonly onRetry: (() => void) | null;
}): ReactElement {
  return (
    <div className="mt-3">
      <Outcome sent={sent} doing={doing} nothingHappened={nothingHappened} receipt={receipt} />
      {onRetry === null ? null : (
        <Button className="mt-2" onClick={onRetry}>
          <RotateCw /> Send the same command again
        </Button>
      )}
    </div>
  );
}

function Outcome({
  sent,
  doing,
  nothingHappened,
  receipt,
}: {
  readonly sent: Answer<{ readonly durability_state: DurabilityState }>;
  readonly doing: string;
  readonly nothingHappened: string;
  readonly receipt: ReactNode;
}): ReactElement {
  switch (sent.kind) {
    case "asking":
      return <Asking what={doing} />;
    case "refused":
      return <Refused problem={sent.problem} action={nothingHappened} />;
    case "unreachable":
      return (
        <Unreachable
          detail={sent.detail}
          action="Whether this was written is not known. Sending again reuses the same command, so it cannot write twice."
        />
      );
    case "malformed":
      return <Malformed detail={sent.detail} />;
    case "answered":
      return <>{receipt}</>;
  }
}

/**
 * A write ctower took but has not confirmed is durable. It is not done until
 * it says so, and the page says exactly that rather than showing a version
 * that has not moved.
 */
export function NotYetDurable(): ReactElement {
  return (
    <p className="m-0 text-sm text-muted">
      ctower took the command and has not confirmed it is durable.
    </p>
  );
}
