import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { Button } from "../../ui/primitives";
import { leaving } from "../../workflows/graph";
import { splitReference, workflowFacts } from "../../workflows/read";
import { Sent } from "../Sent";
import { useMove } from "../useMove";
import type { StandingWorkflow } from "../workflow";
import { stageWord } from "../words";

/**
 * Where this ticket goes next, offered rather than typed.
 *
 * The shipped control asked the operator to type a stage, because nothing was
 * thought to answer with a workflow's graph. The frozen spec supersedes that: a
 * workflow is a component of the company document, so the ways out of the stage
 * this ticket stands at are declared, and each is offered by the job it names.
 *
 * Whether a move is legal is still the record's to decide — a transition
 * carries a predicate this console does not evaluate — so a refusal renders in
 * the record's own words instead of being pre-judged here. A workflow this
 * company records no definition for offers nothing, because a guess at a
 * destination is a command sent blind.
 */
export function MoveOn({
  ticketId,
  standing,
  document,
  onMoved,
}: {
  readonly ticketId: string;
  readonly standing: StandingWorkflow;
  readonly document: CompanyBundleDocument;
  readonly onMoved: () => void;
}): ReactElement | null {
  const move = useMove(ticketId, standing, onMoved);
  const ways = nextOf(standing, document);

  if (standing.closed) {
    return (
      <p className="mt-3 mb-0 text-xs text-muted">
        This is finished. It stops at {stageWord(standing.stage)}.
      </p>
    );
  }
  if (ways.length === 0) {
    return null;
  }

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">Move it on to</span>
        {ways.map((stage) => (
          <Button
            key={stage}
            size="sm"
            aria-pressed={move.destination === stage}
            className={move.destination === stage ? "border-amber font-semibold" : undefined}
            onClick={(): void => {
              move.setDestination(stage);
            }}
          >
            {stageWord(stage)}
          </Button>
        ))}
        <Button variant="primary" size="sm" disabled={!move.armed} onClick={move.send}>
          Move it
        </Button>
      </div>
      {move.sent === null ? null : (
        <Sent
          sent={move.sent}
          doing="Moving this ticket"
          nothingHappened="It did not move. It is still where it was."
          onRetry={move.retry}
          receipt={
            move.sent.kind === "answered" ? (
              <p className="m-0 text-sm text-muted">
                {move.sent.value.durability_state === "accepted"
                  ? `Now at ${stageWord(move.sent.value.stage)}.`
                  : "ctower took the move and has not confirmed it is durable."}
              </p>
            ) : null
          }
        />
      )}
    </div>
  );
}

/** Every stage the workflow declares a way to from where this ticket stands. */
function nextOf(standing: StandingWorkflow, document: CompanyBundleDocument): readonly string[] {
  const [key] = splitReference(standing.reference);
  const workflow = workflowFacts(document).find((fact) => fact.key === key);
  if (workflow === undefined) {
    return [];
  }
  return leaving(workflow.transitions, standing.stage).map((transition) => transition.to);
}
