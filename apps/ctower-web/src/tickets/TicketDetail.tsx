import { ArrowLeft } from "lucide-react";
import type { ReactElement } from "react";
import type { BoardCard } from "@ctower/client";
import { Button, Card, CardBody, Chip, Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { Instant, laneWord, PriorityChip } from "./facts";
import { History } from "./History";
import { MoveStage } from "./MoveStage";
import { StageLadder } from "./StageLadder";
import { Changes, Labels, TicketFacts } from "./TicketFacts";
import type { OneTicket } from "./reads";
import { workflowFrom } from "./workflow";

/**
 * One ticket, as a page.
 *
 * The operator's mockup is the shape: the ticket names itself, the stages it
 * has walked sit at the top, what has happened runs down the middle, and the
 * facts sit beside it. Three of the mockup's sections are not here — acceptance
 * criteria, evidence slots and the custody bar — because the authored contract
 * declares no read that answers with them. Drawing empty frames for them would
 * put four invented promises on the operator's screen.
 */
export function TicketDetail({
  one,
  card,
  onBack,
  onMoved,
}: {
  readonly one: OneTicket;
  /** What the board says about this ticket, when it has folded it. */
  readonly card: BoardCard | null;
  readonly onBack: () => void;
  readonly onMoved: () => void;
}): ReactElement {
  const standing = workflowFrom(one.timeline);

  return (
    <>
      <Button variant="quiet" size="sm" className="-ml-2.5 mb-3" onClick={onBack}>
        <ArrowLeft /> Tickets
      </Button>

      <header className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <Mono className="text-fg">
            {one.ticket.display_key ?? one.ticket.ticket_id.slice(0, 8)}
          </Mono>
          <PriorityChip priority={one.ticket.priority} />
          {card === null ? <Chip>not folded yet</Chip> : <Chip>{laneWord(card.lane)}</Chip>}
        </div>
        <h1 className="mt-1.5 mb-0 text-xl leading-tight font-bold tracking-[-0.02em]">
          {one.ticket.title}
        </h1>
      </header>

      {card === null ? null : <Attention card={card} />}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          {standing === null ? <NoWorkflow /> : <StageLadder standing={standing} />}
          {standing === null ? null : (
            <MoveStage ticketId={one.ticket.ticket_id} standing={standing} onMoved={onMoved} />
          )}
          <History timeline={one.timeline} />
        </div>
        <div className="min-w-0 space-y-4">
          <TicketFacts ticket={one.ticket} card={card} />
          {card === null ? null : <Labels card={card} />}
          {card === null ? null : <Changes card={card} />}
        </div>
      </div>
    </>
  );
}

/**
 * The two facts that stop work, drawn where the eye lands first and nowhere
 * else. Each carries the mark its own record earned; a ticket with neither
 * draws nothing here at all.
 */
function Attention({ card }: { readonly card: BoardCard }): ReactElement | null {
  const blocked = card.blocker_reason;
  const waiting = card.human_waiting;
  if (blocked === null && waiting.state !== "waiting") {
    return null;
  }
  return (
    <div className="mb-4 space-y-2">
      {blocked === null ? null : (
        <div className="rounded-md border border-line bg-raised p-3">
          <div className="flex items-start gap-2">
            <Mark name="parked" className="mt-0.5" />
            <div className="min-w-0 flex-1">
              {/* The one line on this page a person actually wrote. */}
              <p className="m-0 text-sm font-medium">{blocked}</p>
              {card.blocker_opened_at === null ? null : (
                <p className="mt-1 mb-0">
                  <Instant at={card.blocker_opened_at} />
                </p>
              )}
            </div>
          </div>
        </div>
      )}
      {waiting.state !== "waiting" ? null : (
        <div className="rounded-md border border-amber/40 bg-amber/10 p-3">
          <div className="flex items-start gap-2">
            <Mark name="warn" className="mt-0.5" />
            <div className="min-w-0 flex-1">
              <p className="m-0 text-sm font-medium">A person is waited on.</p>
              <Mono className="mt-1 block text-muted">
                {waiting.kind_key} · {waiting.reason_code}
              </Mono>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * A ticket nobody has started work on.
 *
 * Starting one is not offered: `startTicketWorkflow` requires a workflow digest
 * and three policy digests, and no operation in the authored contract answers
 * with any of them. A button that could only ever refuse is worse than none.
 */
function NoWorkflow(): ReactElement {
  return (
    <Card>
      <CardBody>
        <p className="m-0 text-sm text-muted">
          No workflow has started on this ticket, so it stands at no stage.
        </p>
      </CardBody>
    </Card>
  );
}
