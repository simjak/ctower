import { RotateCw } from "lucide-react";
import type { ReactElement } from "react";
import type { InboxSendResult } from "@ctower/client";
import type { Answer } from "../api/client";
import { Button, Chip, Mono } from "../ui/primitives";
import { Unanswered } from "./Unanswered";

/**
 * What came back from a send, and the one thing it may not do: call a pending
 * write delivered.
 *
 * `durability_pending` means ctower took the message and has not confirmed it
 * survives, so it is drawn as taken and not as sent — and the thread above may
 * honestly not show it yet. Silence is the other case that matters: the message
 * may or may not have been written, and sending again carries the same
 * idempotency key, which is why the screen can offer that instead of telling
 * the operator to reload and find out.
 */
export function Sent({
  outcome,
  again,
}: {
  readonly outcome: Answer<InboxSendResult> | null;
  readonly again: (() => void) | null;
}): ReactElement | null {
  if (outcome === null) {
    return null;
  }

  return (
    <div className="space-y-2">
      {/* A refusal and silence do not have the same next action, and this is the
          one place on the page where the difference costs something: a refused
          send wrote nothing, and a send that went unanswered may have written.
          Saying "nothing was written" over silence would be the page's only
          lie. */}
      <Unanswered
        answer={outcome}
        what="Sending"
        action={
          outcome.kind === "unreachable"
            ? "Whether this was written is not known. Sending it again carries the same command, so it cannot write twice."
            : "Nothing was written. Change the message and send it again."
        }
      />
      {outcome.kind === "answered" ? <Receipt result={outcome.value} /> : null}
      {again === null ? null : (
        <Button variant="ghost" size="sm" onClick={again}>
          <RotateCw /> Send the same message again
        </Button>
      )}
    </div>
  );
}

function Receipt({ result }: { readonly result: InboxSendResult }): ReactElement {
  const accepted = result.durability_state === "accepted";
  return (
    <p className="m-0 flex flex-wrap items-center gap-2 text-xs text-muted">
      {accepted ? <Chip tone="ok">sent</Chip> : <Chip tone="amber">not yet durable</Chip>}
      <span>
        {accepted
          ? "Recorded as message"
          : "ctower took it and has not confirmed it is durable. It is message"}
      </span>
      <Mono>#{result.position}</Mono>
      <span>to</span>
      <Mono>{result.to}</Mono>
    </p>
  );
}
