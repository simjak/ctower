import { useCallback, useState } from "react";
import { ChevronLeft } from "lucide-react";
import type { ReactElement } from "react";
import type { BoardCard, CompanyBundleDocument } from "@ctower/client";
import { useAudit } from "../../audit/useAudit";
import { Button, Chip } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import type { OneTicket } from "../reads";
import { workflowFrom } from "../workflow";
import { laneTone, laneWord, numberWord, priorityWord, whenWords } from "../words";
import { Beside } from "./Beside";
import { Custody } from "./Custody";
import { Ladder } from "./Ladder";
import { MoveOn } from "./MoveOn";
import { Notes } from "./Said";
import { Proof } from "./Proof";
import { Section } from "./parts";
import { Why } from "./Why";

/**
 * One ticket, as the page the operator drew.
 *
 * The sections are his, in his order: what needs attention, how far it has got,
 * why it exists, what it has to prove, who has had it, what has been said, and
 * beside them the work and how it is going. Each is backed by a declared read
 * and says in one line where the record stops — the criteria's text, the person
 * behind an identifier, a file on a ticket. Nothing is drawn as an empty frame.
 *
 * The audit read is held here rather than in each section, because two sections
 * are two readings of one answer: the proof events and the notes come from the
 * same pages, and asking twice would let them disagree about what has happened.
 */
export function TicketHome({
  one,
  card,
  project,
  document,
  onBack,
  onMoved,
}: {
  readonly one: OneTicket;
  /** What the board says about this ticket, when it has folded it. */
  readonly card: BoardCard | null;
  readonly project: string;
  /** The company record, which carries the workflow this ticket runs. */
  readonly document: CompanyBundleDocument;
  readonly onBack: () => void;
  readonly onMoved: () => void;
}): ReactElement {
  const [reloadKey, setReloadKey] = useState(0);
  const audit = useAudit(project, one.ticket.ticket_id, reloadKey);
  const standing = workflowFrom(one.timeline);
  const now = Date.now();
  const reread = useCallback((): void => {
    setReloadKey((count) => count + 1);
  }, []);

  return (
    <>
      <nav aria-label="Trail" className="mb-4 flex items-center gap-1.5 text-2xs text-muted">
        <Button variant="quiet" size="sm" className="-ml-2.5" onClick={onBack}>
          <ChevronLeft /> Tickets
        </Button>
        <span aria-hidden>›</span>
        <span className="text-fg">{numberWord(one.ticket.display_key)}</span>
      </nav>

      <div className="flex flex-wrap items-center gap-2">
        {card === null ? (
          <Chip>not on the board yet</Chip>
        ) : (
          <Chip tone={laneTone(card.lane)}>{laneWord(card.lane)}</Chip>
        )}
        {one.ticket.priority === "P0" ? <Chip tone="amber">{priorityWord("P0")}</Chip> : null}
        <span className="flex-1" />
        <span className="text-xs text-muted">
          Raised {whenWords(one.ticket.created_at, now).toLowerCase()}
        </span>
      </div>
      <h1 className="mt-1.5 mb-6 max-w-[34ch] text-2xl leading-tight font-bold tracking-[-0.022em]">
        {one.ticket.title}
      </h1>

      {card === null ? null : <Attention card={card} />}

      {standing === null ? (
        <Section title="How far it has got">
          <p className="m-0 text-sm text-muted">
            No workflow has started on this ticket, so it stands at no step yet.
          </p>
        </Section>
      ) : (
        <Ladder standing={standing} document={document}>
          <MoveOn
            ticketId={one.ticket.ticket_id}
            standing={standing}
            document={document}
            onMoved={onMoved}
          />
        </Ladder>
      )}

      <div className="grid gap-x-10 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <Why projectKey={project} ticketId={one.ticket.ticket_id} now={now} />
          <Proof events={audit.events} now={now} />
          <Custody projectKey={project} ticketId={one.ticket.ticket_id} now={now} />
          <Notes ticketId={one.ticket.ticket_id} events={audit.events} now={now} onSaid={reread} />
        </div>
        <div className="min-w-0">
          <Beside ticket={one.ticket} card={card} standing={standing} now={now} />
        </div>
      </div>
    </>
  );
}

/**
 * The one amber block on the page, and the only place the eye is asked to land
 * first. A ticket with neither a blocker nor a person being waited on draws
 * nothing here at all — an attention box that is always present is not one.
 */
function Attention({ card }: { readonly card: BoardCard }): ReactElement | null {
  const blocked = card.blocker_reason;
  const waiting = card.human_waiting.state === "waiting";
  if (blocked === null && !waiting) {
    return null;
  }
  return (
    <div className="mt-1 mb-8 flex items-start gap-3 rounded-md border border-amber/35 bg-amber/10 p-4">
      <Mark name={blocked === null ? "warn" : "parked"} className="mt-0.5" />
      <div className="min-w-0">
        {/* The blocker's own words are the one line on this page a person
            actually wrote, so they are quoted rather than summarised. */}
        <p className="m-0 text-md font-semibold text-amber-ink">
          {blocked ?? "Somebody is being waited on before this can move."}
        </p>
        {blocked !== null && waiting ? (
          <p className="mt-1 mb-0 text-sm text-amber-ink/85">
            Somebody is being waited on as well.
          </p>
        ) : null}
      </div>
    </div>
  );
}
