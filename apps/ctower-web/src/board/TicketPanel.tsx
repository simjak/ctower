import { Tabs } from "radix-ui";
import type { ReactElement } from "react";
import type { BoardCard, TicketResource } from "@ctower/client";
import { AuditTab } from "../audit/AuditTab";
import { cn } from "../ui/cn";
import { Button, Chip, Mono } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import type { Answer } from "../api/client";
import { useTicket } from "./useBoard";

/**
 * What is behind a card, on two reads that answer different questions.
 *
 * `Ticket` is the ticket as it stands right now. `Work` is how it got there —
 * the audit read, which carries the intents, the proof moves and the crew
 * sessions the timeline read does not. They are two tabs and not one list
 * because they are two different questions, and stacking them would make the
 * standing facts scroll away under the history.
 *
 * Nothing here writes. Transitions belong to the ticket lane; this panel reads.
 */
export function TicketPanel({
  projectKey,
  card,
  onClose,
}: {
  readonly projectKey: string;
  readonly card: BoardCard;
  readonly onClose: () => void;
}): ReactElement {
  const ticket = useTicket(projectKey, card.ticket_id);

  return (
    <aside className="sticky top-18 overflow-hidden rounded-md border border-line bg-card">
      <header className="flex items-start gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          {card.display_key === null ? null : (
            <Mono className="block text-muted">{card.display_key}</Mono>
          )}
          <h2 className="m-0 mt-0.5 text-md leading-snug font-semibold">{card.title}</h2>
        </div>
        <Button size="sm" variant="quiet" onClick={onClose} aria-label="Close this ticket">
          Close
        </Button>
      </header>
      <Tabs.Root defaultValue="ticket">
        <Tabs.List className="flex gap-1 border-b border-line px-3" aria-label="This ticket">
          <Tab value="ticket">Ticket</Tab>
          <Tab value="work">Work</Tab>
        </Tabs.List>
        <Tabs.Content value="ticket" className="px-4 py-3">
          <TicketFacts card={card} ticket={ticket} />
        </Tabs.Content>
        <Tabs.Content value="work" className="max-h-[60dvh] overflow-y-auto py-1">
          <AuditTab projectKey={projectKey} ticketId={card.ticket_id} />
        </Tabs.Content>
      </Tabs.Root>
    </aside>
  );
}

function Tab({
  value,
  children,
}: {
  readonly value: string;
  readonly children: string;
}): ReactElement {
  return (
    <Tabs.Trigger
      value={value}
      className={cn(
        "-mb-px cursor-pointer border-b-2 border-transparent px-2 py-2 text-sm text-muted",
        "data-[state=active]:border-amber data-[state=active]:font-semibold data-[state=active]:text-fg"
      )}
    >
      {children}
    </Tabs.Trigger>
  );
}

/**
 * The standing facts, from the ticket read and from the card's own projection.
 *
 * The two are kept apart on purpose. `durability_state` is the ticket read's,
 * and it is drawn because a command that is committed but not yet durable is a
 * real state an operator will otherwise mistake for a stale screen.
 */
function TicketFacts({
  card,
  ticket,
}: {
  readonly card: BoardCard;
  readonly ticket: Answer<TicketResource>;
}): ReactElement {
  return (
    <div>
      <dl className="m-0 grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-1.5">
        <Row label="Lane">
          <span className="text-sm">{card.lane.replace(/_/g, " ")}</span>
        </Row>
        <Row label="Priority">
          <Chip tone={card.priority === "P0" ? "amber" : "neutral"}>{card.priority}</Chip>
        </Row>
        {card.stage_label === null ? null : (
          <Row label="Stage">
            <Mono className="text-muted">{card.stage_label}</Mono>
          </Row>
        )}
        {card.blocker_reason === null ? null : (
          <Row label="Blocked by">
            <span className="text-sm">{card.blocker_reason}</span>
          </Row>
        )}
        <Row label="Custodian">
          <Mono className="break-words text-muted">{card.custodian_id}</Mono>
        </Row>
        {card.applied_labels.length === 0 ? null : (
          <Row label="Labels">
            <span className="flex flex-wrap gap-1">
              {card.applied_labels.map((label) => (
                <Chip key={label.label_key}>{label.label}</Chip>
              ))}
            </span>
          </Row>
        )}
        {card.change_references.map((reference) => (
          <Row key={reference.reference} label="Change">
            <Mono className="break-words text-muted">{reference.reference}</Mono>
          </Row>
        ))}
      </dl>
      <Standing ticket={ticket} />
    </div>
  );
}

/**
 * The three facts only the ticket read carries, and the state of that read.
 *
 * It sits under the card's own facts rather than among them, because a refusal
 * on this read is a refusal about the ticket and not about the row it would have
 * filled — a state squeezed into a definition cell reads as a missing value.
 */
function Standing({ ticket }: { readonly ticket: Answer<TicketResource> }): ReactElement {
  switch (ticket.kind) {
    case "asking":
      return <Asking what="Reading this ticket" />;
    case "refused":
      return (
        <div className="mt-3">
          <Refused problem={ticket.problem} action="Reopen the card to ask again." />
        </div>
      );
    case "unreachable":
      return (
        <div className="mt-3">
          <Unreachable detail={ticket.detail} action="Reopen the card to ask again." />
        </div>
      );
    case "malformed":
      return (
        <div className="mt-3">
          <Malformed detail={ticket.detail} />
        </div>
      );
    case "answered":
      return (
        <dl className="m-0 mt-1.5 grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-1.5">
          <Row label="Raised">
            <Mono className="text-muted">
              {ticket.value.created_at.slice(0, 19).replace("T", " ")}
            </Mono>
          </Row>
          <Row label="Source">
            <Mono className="break-words text-muted">
              {ticket.value.source.kind} · {ticket.value.source.ref}
            </Mono>
          </Row>
          <Row label="Recorded">
            {ticket.value.durability_state === "accepted" ? (
              <Chip tone="ok">Durable</Chip>
            ) : (
              <Chip tone="amber">Pending</Chip>
            )}
          </Row>
        </dl>
      );
  }
}

function Row({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactElement | readonly ReactElement[];
}): ReactElement {
  return (
    <div className="contents">
      <dt className="pt-0.5 text-2xs text-muted">{label}</dt>
      <dd className="m-0 min-w-0">{children}</dd>
    </div>
  );
}
