import { X } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import type { ReactElement, ReactNode } from "react";
import type { BoardCard, TicketResource } from "@ctower/client";
import type { Answer } from "../api/client";
import { AuditFeed } from "../audit/AuditFeed";
import { Hint } from "../ui/form";
import { Button, Chip, Mono } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { cardElementId } from "./CardTile";
import { instant } from "./history";
import { laneLabel } from "./lanes";
import { useTicket } from "./useBoard";

/**
 * What one card is, read out of the record.
 *
 * The panel itself reads and never writes. The one command that can reach a
 * card — the move its workflow declares next — arrives as a section the stage
 * view passes in, with its own authority, its own idempotency key and its own
 * refusals, and it is absent from the lane view because a lane is not a stage.
 *
 * The card the operator clicked already carries a title, a lane and a priority,
 * so those are drawn from it immediately and the two reads fill in what only
 * the record knows. A read that is still out says so; a read that was refused
 * renders as a refusal, in the registry's own words.
 */
export function TicketPanel({
  card,
  projectKey,
  advance,
  onClose,
}: {
  readonly card: BoardCard;
  readonly projectKey: string;
  /**
   * The one move the workflow declares out of this card's stage, when the
   * screen that opened this panel is the one that draws stages. The lane view
   * passes none: a lane is not a stage, and a move out of `in_progress` is not
   * a thing the record declares.
   */
  readonly advance?: ReactNode;
  readonly onClose: () => void;
}): ReactElement {
  const ticket = useTicket(projectKey, card.ticket_id);

  return (
    <DialogPrimitive.Root
      open
      onOpenChange={(next): void => {
        if (!next) {
          onClose();
        }
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-20 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          // Closing puts the keyboard back on the card it was opened from.
          // Without this the panel has no trigger to restore to and `Escape`
          // drops focus on the document, which sends a keyboard operator back
          // to the top of the shell to find their place again.
          onCloseAutoFocus={(event): void => {
            event.preventDefault();
            window.document.getElementById(cardElementId(card.ticket_id))?.focus();
          }}
          className="fixed inset-y-0 right-0 z-30 flex w-[440px] max-w-[92vw] flex-col border-l border-line bg-card outline-none"
        >
          <header className="flex items-start gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex flex-wrap items-center gap-1.5">
                {card.display_key === null ? null : (
                  <Mono className="text-muted">{card.display_key}</Mono>
                )}
                <Chip tone={card.priority === "P0" ? "amber" : "neutral"}>{card.priority}</Chip>
              </div>
              <DialogPrimitive.Title className="m-0 text-md leading-snug font-semibold">
                {card.title}
              </DialogPrimitive.Title>
            </div>
            <DialogPrimitive.Close asChild>
              <Button variant="quiet" size="sm" aria-label="Close">
                <X />
              </Button>
            </DialogPrimitive.Close>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            <Section title="This ticket">
              <Recorded card={card} ticket={ticket} />
            </Section>
            {/* This section used to read `getTicketTimeline`, and carried a
                comment saying so: the timeline answers the ticket's own events
                and its workflow's, while "a blocker and an admission are
                recorded on a third stream and are not in it", so a section
                headed History quietly omitted them. `listTicketAuditEvents`
                answers all three streams — nine event kinds where the timeline
                had four — so the section now reads that instead of standing
                beside it. Two overlapping histories on one panel would be two
                answers to one question, and the smaller one was the one that
                had to say what it was missing. */}
            {advance === undefined ? null : advance}
            <Section title="Work" hint="Every act the record kept against this ticket.">
              <AuditFeed projectKey={projectKey} ticketId={card.ticket_id} />
            </Section>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function Section({
  title,
  hint,
  children,
}: {
  readonly title: string;
  readonly hint?: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <section className="mb-5 last:mb-0">
      <div className="mb-2 flex items-center gap-1.5">
        <h3 className="m-0 text-2xs leading-none font-medium text-muted">{title}</h3>
        {hint === undefined ? null : <Hint text={hint} />}
      </div>
      {children}
    </section>
  );
}

/**
 * The card's own facts, then the ticket read's.
 *
 * `getBoard` and `getTicket` answer about the same ticket from two sides — the
 * projection and the record — so the panel says which side each line came from
 * by only ever drawing a field once, from the read that owns it.
 */
function Recorded({
  card,
  ticket,
}: {
  readonly card: BoardCard;
  readonly ticket: Answer<TicketResource>;
}): ReactElement {
  return (
    <div className="space-y-1.5">
      {/* Lane and stage are two different facts and they are labelled, not
          chipped: `complete` and `close` side by side as bare chips read as one
          state said twice, and the panel covers the column that would otherwise
          answer where this card sits. */}
      <Said label="Lane" value={laneLabel(card.lane)} />
      {card.stage_label === null ? null : <Line label="Stage" value={card.stage_label} />}
      <Line label="Custodian" value={card.custodian_id} />
      {card.assignee_id === null ? null : <Line label="Assignee" value={card.assignee_id} />}
      {card.blocker_reason === null ? null : (
        <Said label="Blocked by" value={card.blocker_reason} />
      )}
      <Detail ticket={ticket} />
    </div>
  );
}

function Detail({ ticket }: { readonly ticket: Answer<TicketResource> }): ReactElement {
  switch (ticket.kind) {
    case "asking":
      return <Asking what="Reading this ticket" />;
    case "refused":
      return <Refused problem={ticket.problem} action="Nothing else about it was read." />;
    case "unreachable":
      return <Unreachable detail={ticket.detail} action="Close and open it again to ask again." />;
    case "malformed":
      return <Malformed detail={ticket.detail} />;
    case "answered":
      return (
        <>
          <Line
            label="Raised"
            value={instant(ticket.value.created_at)}
            title={ticket.value.created_at}
          />
          <Line
            label="Came from"
            value={`${ticket.value.source.kind} · ${ticket.value.source.ref}`}
          />
          <Line label="Version" value={String(ticket.value.version)} />
          {ticket.value.durability_state === "accepted" ? null : (
            <div className="pt-1">
              <Chip tone="amber">not yet durable</Chip>
            </div>
          )}
        </>
      );
  }
}

/**
 * One recorded fact. `Line` is the machine's — a key, an identifier, a
 * reference, an instant — and `Said` is a person's. A sentence somebody typed
 * set in the machine typeface reads as though ctower generated it, and a
 * blocker's reason is the one line on this panel a human actually wrote.
 */
function Line({
  label,
  value,
  title,
}: {
  readonly label: string;
  readonly value: string;
  readonly title?: string;
}): ReactElement {
  return (
    <Row label={label}>
      <Mono className="min-w-0 flex-1 truncate text-fg" title={title ?? value}>
        {value}
      </Mono>
    </Row>
  );
}

function Said({ label, value }: { readonly label: string; readonly value: string }): ReactElement {
  return (
    <Row label={label}>
      <span className="min-w-0 flex-1 text-sm text-fg">{value}</span>
    </Row>
  );
}

function Row({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-24 shrink-0 text-xs text-muted">{label}</span>
      {children}
    </div>
  );
}
