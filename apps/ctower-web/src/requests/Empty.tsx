import type { ReactElement } from "react";
import type { CtowerProjectCutoverHealth } from "@ctower/client";
import type { Answer } from "../api/client";
import { Mark } from "../ui/marks";
import { Button, Mono } from "../ui/primitives";
import { captureOpen } from "./useCarryOver";

/**
 * The ledger answered, completely, with nothing.
 *
 * This is the state the shadow tower is actually in, so it is the one that has
 * to be unmistakable: an empty read and a failed read are different facts, and
 * an operator who cannot tell them apart cannot trust either. The mark is
 * `idle` — a queue with nothing in it is a recorded state, not a missing one —
 * and the sentence beneath it is never this screen's own theory. It is what the
 * carry-over read said, quoted in the line below it.
 */
export function Empty({
  carryOver,
  onReadAgain,
}: {
  readonly carryOver: Answer<CtowerProjectCutoverHealth>;
  readonly onReadAgain: () => void;
}): ReactElement {
  return (
    <div className="rounded-md border border-line bg-raised p-4">
      <div className="flex items-start gap-2">
        <Mark name="idle" className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="m-0 text-sm font-medium text-fg">No requests are recorded here.</p>
          <Because carryOver={carryOver} />
          <Button className="mt-3" size="sm" variant="primary" onClick={onReadAgain}>
            Read again
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Why, and only as far as ctower said.
 *
 * A tenant that predates the Request cutover cannot take a capture until that
 * cutover completes, so on this tower the empty ledger has a recorded cause and
 * the operator should read it here rather than conclude the screen is broken.
 * When the carry-over read refuses or says nothing, this says so and stops —
 * an emptiness with no readable cause is not an emptiness with the usual one.
 */
function Because({
  carryOver,
}: {
  readonly carryOver: Answer<CtowerProjectCutoverHealth>;
}): ReactElement | null {
  switch (carryOver.kind) {
    case "asking":
      return null;
    case "answered":
      return (
        <>
          <p className="mt-1 mb-0 text-sm text-muted">
            {captureOpen(carryOver.value)
              ? "The ledger is open and no one has filed anything against this tower."
              : "The old ledger has not been carried over into this tower, and until it is nothing can be filed here."}
          </p>
          <Mono className="mt-1 block text-muted">carry-over · {carryOver.value.phase}</Mono>
        </>
      );
    case "refused":
    case "unreachable":
    case "malformed":
      return <p className="mt-1 mb-0 text-sm text-muted">ctower did not say why.</p>;
  }
}
