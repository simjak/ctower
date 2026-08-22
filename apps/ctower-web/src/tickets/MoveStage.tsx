import type { ReactElement } from "react";
import type { WorkflowReceipt } from "@ctower/client";
import { Field } from "../ui/form";
import { Button, Card, CardBody, CardHeader, CardTitle, Chip, Input, Mono } from "../ui/primitives";
import { Fact } from "./facts";
import { NotYetDurable, Sent } from "./Sent";
import { useMove } from "./useMove";
import type { StandingWorkflow } from "./workflow";

/**
 * Moving the ticket to another stage.
 *
 * The operator types where it goes. That is not a gap left open for later: the
 * authored contract declares no read that returns a workflow's stages, so a
 * menu here would be this console's guess at a graph, and `ctowerctl ticket
 * transition --destination-stage` asks for the same thing for the same reason.
 * Everything else on the command is read from the record, and shown, so what
 * is being sent is never hidden behind the button.
 *
 * A refusal is the expected answer to an illegal move, and it renders as the
 * record's own words. The predicate on a transition is the record's to enforce;
 * this page does not pre-judge it.
 */
export function MoveStage({
  ticketId,
  standing,
  onMoved,
}: {
  readonly ticketId: string;
  readonly standing: StandingWorkflow;
  readonly onMoved: () => void;
}): ReactElement {
  const move = useMove(ticketId, standing, onMoved);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Move stage</CardTitle>
        <span className="flex-1" />
        {standing.closed ? <Chip>closed</Chip> : null}
      </CardHeader>
      <CardBody>
        {standing.closed ? (
          <p className="m-0 text-sm text-muted">
            The record closed this ticket at <Mono>{standing.stage}</Mono>. A closed workflow does
            not move.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-56 min-w-0">
                <Field
                  label="TO STAGE"
                  hint="The stage this ticket moves to, named as the workflow names it."
                >
                  <Input
                    className="mono"
                    value={move.destination}
                    aria-label="Destination stage"
                    onChange={(event): void => {
                      move.setDestination(event.target.value);
                    }}
                  />
                </Field>
              </div>
              <Button variant="primary" disabled={!move.armed} onClick={move.send}>
                Move it
              </Button>
            </div>
            {/* Everything the command carries besides the destination, in the
                one line D9 allows — so what is sent is never behind the
                button, and the stage is not said a third time in a placeholder
                that would read as a value already filled in. */}
            <p className="mt-2 mb-0 text-2xs text-muted">
              Recorded on send, from <Mono>{standing.stage}</Mono> at version{" "}
              <Mono>{standing.version}</Mono>. ctower refuses a move its workflow does not allow.
            </p>
          </>
        )}
        {move.sent === null ? null : (
          <Sent
            sent={move.sent}
            doing="Moving this ticket"
            nothingHappened="The ticket did not move. It is still where it was."
            onRetry={move.retry}
            receipt={move.sent.kind === "answered" ? <Moved receipt={move.sent.value} /> : null}
          />
        )}
      </CardBody>
    </Card>
  );
}

function Moved({ receipt }: { readonly receipt: WorkflowReceipt }): ReactElement {
  const accepted = receipt.durability_state === "accepted";
  return (
    <div className="rounded-md border border-line bg-raised p-3">
      {/* A pending write may not be narrated as a present fact. "now at frame"
          under a chip that says the record has not confirmed it contradicts
          itself, and the ladder above still shows the stage it left. */}
      <p className="m-0 flex items-center gap-2 text-sm">
        {accepted ? <Chip tone="ok">moved</Chip> : <Chip tone="amber">not yet durable</Chip>}
        <span>
          {accepted ? "now at " : "asked for "}
          <Mono>{receipt.stage}</Mono>
        </span>
      </p>
      {accepted ? null : (
        <div className="mt-1.5">
          <NotYetDurable />
        </div>
      )}
      <div className="mt-2">
        <Fact label="run">
          <Mono className="break-all">{receipt.workflow_run_id}</Mono>
        </Fact>
        <Fact label="version">
          <Mono>{receipt.version}</Mono>
        </Fact>
        {receipt.lifecycle_facts.length === 0 ? null : (
          <Fact label="lifecycle">
            <Mono>{receipt.lifecycle_facts.join(" · ")}</Mono>
          </Fact>
        )}
      </div>
    </div>
  );
}
