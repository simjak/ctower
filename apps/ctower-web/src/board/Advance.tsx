import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument, MovementEvent, WorkflowReceipt } from "@ctower/client";
import type { Answer } from "../api/client";
import { Button, Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { useTicket } from "../tickets/reads";
import { useMove } from "../tickets/useMove";
import { workflowFrom } from "../tickets/workflow";
import type { StandingWorkflow } from "../tickets/workflow";
import { conveyorOf } from "./conveyor";

/**
 * The move this card's workflow declares next, and what the record says when it
 * is asked for it.
 *
 * This is the half that makes the conveyor a workflow rather than an animation.
 * The stage a ticket may move to is not typed here and not guessed: the company
 * definition declares a transition out of the stage this ticket stands at, and
 * that transition is the destination. What the definition cannot say is whether
 * *this* ticket satisfies the gate — only ctower can answer that, and it
 * answers when the move is attempted. So a card that cannot advance says so in
 * the record's own words, on the card, after asking.
 *
 * Nothing is pre-judged. There is no "blocked" badge computed here, because no
 * read in the authored contract evaluates a predicate against a ticket.
 */
export function Advance({
  company,
  projectKey,
  ticketId,
  stageKey,
  movement,
  onMoved,
}: {
  readonly company: CompanyBundleDocument;
  readonly projectKey: string;
  readonly ticketId: string;
  /** Where the board says this card stands; null when the record places it nowhere. */
  readonly stageKey: string | null;
  readonly movement: readonly MovementEvent[];
  readonly onMoved: () => void;
}): ReactElement | null {
  const [reloadKey, setReloadKey] = useState(0);
  const one = useTicket(projectKey, ticketId, reloadKey);
  const conveyor = conveyorOf(company, [], movement);
  const declared = conveyor.stages.find((stage) => stage.key === stageKey)?.leaving ?? null;

  if (stageKey === null) {
    return (
      <Section>
        <p className="m-0 text-sm text-muted">
          The record places this ticket at no stage, so there is no move to make from here. A
          workflow is started on a ticket, and nothing has started one on this.
        </p>
      </Section>
    );
  }

  if (conveyor.workflow === null) {
    return (
      <Section>
        <p className="m-0 text-sm text-muted">{conveyor.silence}</p>
      </Section>
    );
  }

  if (declared === null) {
    return (
      <Section>
        <p className="m-0 text-sm text-muted">
          <Mono>{conveyor.workflow.key}</Mono> declares no move out of <Mono>{stageKey}</Mono>.
          Nothing here can move it, and drawing a control that reaches nothing would say otherwise.
        </p>
      </Section>
    );
  }

  switch (one.kind) {
    case "asking":
      return (
        <Section>
          <Asking what="Reading what this ticket has done" />
        </Section>
      );
    case "refused":
      return (
        <Section>
          <Refused problem={one.problem} action="The move needs this read. Ask again." />
        </Section>
      );
    case "unreachable":
      return (
        <Section>
          <Unreachable detail={one.detail} action="Nothing was read, and nothing was sent." />
        </Section>
      );
    case "malformed":
      return (
        <Section>
          <Malformed detail={one.detail} />
        </Section>
      );
    case "answered": {
      const standing = workflowFrom(one.value.timeline);
      return (
        <Section>
          <Attempt
            ticketId={ticketId}
            standing={standing}
            destination={declared.to}
            predicate={declared.predicate}
            onMoved={(): void => {
              setReloadKey((count) => count + 1);
              onMoved();
            }}
          />
        </Section>
      );
    }
  }
}

/**
 * One attempt at the declared move.
 *
 * The command carries four facts and three of them are read: the workflow, the
 * stage the record has this ticket standing at, and the version that move must
 * expect. The fourth is where it goes, and the definition said that. So the
 * button says what it will do and the facts under it say what is being sent.
 */
function Attempt({
  ticketId,
  standing,
  destination,
  predicate,
  onMoved,
}: {
  readonly ticketId: string;
  readonly standing: StandingWorkflow | null;
  readonly destination: string;
  readonly predicate: string | null;
  readonly onMoved: () => void;
}): ReactElement {
  if (standing === null) {
    return (
      <p className="m-0 text-sm text-muted">
        This ticket&rsquo;s history carries no workflow event, so the version a move must expect is
        not known and nothing may be sent.
      </p>
    );
  }
  return (
    <Armed
      ticketId={ticketId}
      standing={standing}
      destination={destination}
      predicate={predicate}
      onMoved={onMoved}
    />
  );
}

function Armed({
  ticketId,
  standing,
  destination,
  predicate,
  onMoved,
}: {
  readonly ticketId: string;
  readonly standing: StandingWorkflow;
  readonly destination: string;
  readonly predicate: string | null;
  readonly onMoved: () => void;
}): ReactElement {
  const move = useMove(ticketId, standing, onMoved);
  const armed = !standing.closed && move.destination === destination;

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          disabled={standing.closed}
          onClick={(): void => {
            move.setDestination(destination);
          }}
        >
          Ask to move to {destination}
        </Button>
        {armed ? (
          <Button variant="ghost" onClick={move.send}>
            Send it
          </Button>
        ) : null}
        {standing.closed ? <Chip>closed</Chip> : null}
      </div>

      <dl className="mt-3 mb-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-2xs text-muted">
        <dt>from</dt>
        <dd className="m-0">
          <Mono>{standing.stage}</Mono>
        </dd>
        <dt>workflow</dt>
        <dd className="m-0">
          <Mono>{standing.reference}</Mono>
        </dd>
        <dt>expects version</dt>
        <dd className="m-0">
          <Mono>{standing.version}</Mono>
        </dd>
        {predicate === null ? null : (
          <>
            <dt>gate</dt>
            <dd className="m-0">
              <Mono title={`The definition requires ${predicate} on this move`}>{predicate}</Mono>
            </dd>
          </>
        )}
      </dl>

      {move.sent === null ? null : <Answered sent={move.sent} onRetry={move.retry} />}
    </>
  );
}

/**
 * What ctower said. A refusal is an answer, not a failure of this screen: an
 * illegal move is exactly what the gate exists to stop, and the reason is the
 * record's own — including which predicate went unsatisfied.
 */
function Answered({
  sent,
  onRetry,
}: {
  readonly sent: Answer<WorkflowReceipt>;
  readonly onRetry: (() => void) | null;
}): ReactElement {
  switch (sent.kind) {
    case "asking":
      return (
        <div className="mt-3">
          <Asking what="Asking the record to move it" />
        </div>
      );
    case "refused":
      return (
        <div className="mt-3">
          <Refused
            problem={sent.problem}
            action="Nothing moved. The gate is the record's to open, not this screen's."
          />
        </div>
      );
    case "unreachable":
      return (
        <div className="mt-3">
          <Unreachable
            detail={sent.detail}
            action="It is not known whether the move was taken. Sending the same command again is safe."
          />
          {onRetry === null ? null : (
            <Button variant="ghost" size="sm" className="mt-2" onClick={onRetry}>
              Send the same command again
            </Button>
          )}
        </div>
      );
    case "malformed":
      return (
        <div className="mt-3">
          <Malformed detail={sent.detail} />
        </div>
      );
    case "answered":
      return (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <Chip tone={sent.value.durability_state === "accepted" ? "ok" : "amber"}>
            {sent.value.durability_state === "accepted" ? "moved" : "not yet durable"}
          </Chip>
          <span className="text-muted">
            now at <Mono>{sent.value.stage}</Mono>, version <Mono>{sent.value.version}</Mono>
          </span>
          {sent.value.durability_state === "accepted" || onRetry === null ? null : (
            <Button variant="ghost" size="sm" onClick={onRetry}>
              Send the same command again
            </Button>
          )}
        </div>
      );
  }
}

function Section({ children }: { readonly children: ReactElement | ReactElement[] }): ReactElement {
  return (
    <Card className="mt-3">
      <CardHeader>
        <CardTitle>Move it on</CardTitle>
      </CardHeader>
      <CardBody>{children}</CardBody>
    </Card>
  );
}
