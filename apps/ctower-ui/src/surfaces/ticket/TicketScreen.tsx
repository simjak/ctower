import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { InlineReading, NoSourceYet, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { laneGlyph, StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter } from "@/read/adapter";
import { cardFor } from "@/read/boardProjection";
import {
  NO_ACCEPTANCE_CRITERIA,
  NO_LABELS,
  NO_RELATIONS_HERE,
  NO_STAGES_HERE,
  NO_TICKET_BRIEF,
  NO_WORKFLOW_REF_HERE,
} from "@/read/futureSources";
import { shortId, stampText } from "@/read/elapsed";
import { namesAnIssueTracker } from "@/read/issueRef";
import type { BoardCard, Reading, RecordEvent, RecordSource, TicketRecord } from "@/read/interface";
import { mapReading } from "@/read/reading";
import { isComment, isRelation, stagesFrom, workflowRefOf } from "@/surfaces/record/events";
import { CommentsPanel, EvidencePanel, RecordStreamPanel } from "./RecordPanels";
import type { EventsReading } from "./RecordPanels";
import { StageStrip } from "./StageStrip";
import { WorkTimeline } from "./WorkTimeline";

/**
 * The whole ticket screen, for both routes that reach one.
 *
 * `/ticket/<id>` opens a named ticket. `/ticket` opens the most recently created
 * one and says so on the page — round-3 QA (#243) found that route *redirecting*
 * to an arbitrary ticket id, which threw away the one sentence that made the
 * behaviour comprehensible and left the operator on a detail page they never
 * chose. A caller passes `note` to state which rule brought the reader here.
 */
function TicketHead({
  ticket,
  card,
}: {
  readonly ticket: TicketRecord;
  readonly card: Reading<BoardCard>;
}): ReactElement {
  return (
    <div className="thead">
      <div className="crumbs">
        <span>{ticket.source.kind}</span>
        <span>/</span>
        <span>{ticket.source.ref}</span>
        <span className="id">{ticket.ticketId}</span>
      </div>
      <h1>
        <InlineReading
          reading={card}
          present={(row) => <StateGlyph name={laneGlyph(row.lane, row.blockerReason !== null)} />}
          missing={() => <StateGlyph name="open" />}
        />
        {ticket.title}
      </h1>
      <div className="tmeta">
        <span className={`pri ${ticket.priority.toLowerCase()}`}>{ticket.priority}</span>
        <InlineReading
          reading={card}
          present={(row) => (
            <>
              <span className="chip">lane {row.lane}</span>
              {row.stageLabel === null ? null : (
                <span className="chip">stage {row.stageLabel}</span>
              )}
            </>
          )}
          missing={(label, detail, tone) => (
            <span className="chip" style={tone} title={detail}>
              board context {label}
            </span>
          )}
        />
        <span className="chip">durability {ticket.durabilityState}</span>
        <span className="chip">version {ticket.version.toString()}</span>
      </div>
      <div className="custody">
        <span className="k">custodian</span>
        <span className="mono" title={`principal ${ticket.custodianId}`}>
          {ticket.custodianName ?? "seat unnamed"}
        </span>
        <span className="k">principal</span>
        <span className="mono">{shortId(ticket.custodianId)}</span>
        {/* a recorded assignee is a present fact and is rendered when the board
            row carries one; round-2 review caught a refactor dropping it */}
        <InlineReading
          reading={card}
          present={(row) =>
            row.assigneeId === null ? null : (
              <>
                <span className="arrow">→</span>
                <span className="k">assignee</span>
                <span className="mono" title={`principal ${row.assigneeId}`}>
                  {row.assigneeName ?? shortId(row.assigneeId)}
                </span>
              </>
            )
          }
          missing={(label, detail, tone) => (
            <>
              <span className="k">assignee</span>
              <span className="mono" style={tone} title={detail}>
                board context {label}
              </span>
            </>
          )}
        />
        <span className="k">created</span>
        <span className="mono">{stampText(ticket.createdAt)}</span>
      </div>
    </div>
  );
}

/**
 * The issue this ticket was raised from, when the record addresses one.
 *
 * The operator asked to see the linked issue. The record's `source` is the only
 * link there is, so this renders a real anchor when the kind names an issue
 * tracker and the ref carries its repository, and otherwise says which of those
 * two is missing. It never composes a URL out of a ref that does not carry a
 * repository — that link would look right and go somewhere else.
 */
function SourceIssue({ source }: { readonly source: RecordSource }): ReactElement {
  if (source.issue !== null) {
    return (
      <a href={source.issue.url} rel="noreferrer noopener" target="_blank">
        {source.issue.label}
      </a>
    );
  }
  if (namesAnIssueTracker(source.kind)) {
    return (
      <span title={`the recorded ref is ${source.ref}`}>
        {source.ref} — this source names an issue tracker, but the ref carries no repository, so
        there is no address to open
      </span>
    );
  }
  return (
    <span title={`the recorded source kind is ${source.kind}`}>
      not raised from an issue tracker — the recorded source is {source.kind}
    </span>
  );
}

function InboxThreadLinks({ threadIds }: { readonly threadIds: readonly string[] }): ReactElement {
  if (threadIds.length === 0) {
    return <span>no inbox thread linked</span>;
  }
  return (
    <span style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      {threadIds.map((threadId) => (
        <Link className="v" href={`/inbox?thread=${encodeURIComponent(threadId)}`} key={threadId}>
          thread {shortId(threadId)}
        </Link>
      ))}
    </span>
  );
}

function HeldBanner({ card }: { readonly card: BoardCard }): ReactElement | null {
  if (card.blockerReason === null) {
    return null;
  }
  return (
    <div className="banner">
      <StateGlyph name="held" />
      <div>
        <h3>held</h3>
        <p>{card.blockerReason}</p>
        <div className="meta">
          {card.blockerOpenedAt === null ? null : (
            <span>
              opened <b>{stampText(card.blockerOpenedAt)}</b>
            </span>
          )}
          <span>
            lane <b>{card.lane}</b>
          </span>
        </div>
      </div>
    </div>
  );
}

function StagesSection({ audit }: { readonly audit: EventsReading }): ReactNode {
  const stages = mapReading(audit, (events) => {
    const entries = stagesFrom(events);
    return entries.length === 0
      ? ({ state: "absent", source: NO_STAGES_HERE } as const)
      : ({ state: "present", value: entries } as const);
  });
  return (
    <Resolved
      reading={stages}
      frame={(declared) => (
        <section className="panel" style={{ marginTop: "18px" }}>
          <header>
            <h2>Stages</h2>
          </header>
          {declared}
        </section>
      )}
    >
      {(entries) => <StageStrip stages={entries} />}
    </Resolved>
  );
}

function AuditNote({ audit }: { readonly audit: EventsReading }): ReactNode {
  return (
    <InlineReading
      reading={audit}
      present={(events: readonly RecordEvent[]) => `${events.length.toString()} appended events`}
      missing={(label, detail) => <span title={detail}>audit {label}</span>}
    />
  );
}

function RightRail({
  ticket,
  card,
  audit,
}: {
  readonly ticket: TicketRecord;
  readonly card: Reading<BoardCard>;
  readonly audit: EventsReading;
}): ReactElement {
  const workflow = mapReading(audit, (events) => {
    const ref = workflowRefOf(events);
    return ref === null
      ? ({ state: "absent", source: NO_WORKFLOW_REF_HERE } as const)
      : ({ state: "present", value: ref } as const);
  });
  const relations = mapReading(audit, (events) => {
    const found = events.filter(isRelation);
    return found.length === 0
      ? ({ state: "absent", source: NO_RELATIONS_HERE } as const)
      : ({ state: "present", value: found } as const);
  });
  return (
    <aside className="rail-r">
      <section className="panel">
        <header>
          <h2>Record</h2>
        </header>
        <ul className="links">
          <li>
            <span className="k">ticket</span>
            <span className="v">{ticket.ticketId}</span>
          </li>
          <li>
            <span className="k">source</span>
            <span className="v">{`${ticket.source.kind} · ${ticket.source.ref}`}</span>
          </li>
          <li>
            <span className="k">inbox</span>
            <span className="v">
              <InlineReading
                reading={card}
                present={(row) => <InboxThreadLinks threadIds={row.inboxThreadIds} />}
                missing={(label, detail) => <span title={detail}>inbox links {label}</span>}
              />
            </span>
          </li>
          <li>
            <span className="k">issue</span>
            <span className="v">
              <SourceIssue source={ticket.source} />
            </span>
          </li>
          <li>
            <span className="k">workflow</span>
            <span className="v">
              <InlineReading
                reading={workflow}
                present={(ref) => ref}
                missing={(label, detail) => <span title={detail}>workflow {label}</span>}
              />
            </span>
          </li>
          <li>
            <span className="k">durability</span>
            <span className="v">{ticket.durabilityState}</span>
          </li>
          <li>
            <span className="k">delivery</span>
            <span className="v">
              <InlineReading
                reading={card}
                present={(row) =>
                  row.deliveryFacts.length === 0
                    ? "no change reference recorded"
                    : row.deliveryFacts.join(" · ")
                }
                missing={(label, detail) => <span title={detail}>board context {label}</span>}
              />
            </span>
          </li>
          <li>
            <span className="k">board</span>
            <Link className="v" href="/board">
              back to the lanes
            </Link>
          </li>
        </ul>
      </section>

      <section className="panel">
        <header>
          <h2>Labels</h2>
        </header>
        <NoSourceYet source={NO_LABELS} />
      </section>

      <section className="panel">
        <header>
          <h2>Depends on</h2>
        </header>
        <Resolved reading={relations}>
          {(events) => (
            <ul className="links">
              {events.map((event) => (
                <li key={event.eventId}>
                  <span className="k">{event.kind}</span>
                  <span className="v">{shortId(event.eventId)}</span>
                </li>
              ))}
            </ul>
          )}
        </Resolved>
      </section>
    </aside>
  );
}

function TicketBody({
  ticket,
  card,
  audit,
  note,
}: {
  readonly ticket: TicketRecord;
  readonly card: Reading<BoardCard>;
  readonly audit: EventsReading;
  readonly note: ReactNode;
}): ReactElement {
  return (
    <>
      <Chrome section="Ticket" back={{ href: "/board", label: "Board" }} />
      <main className="page">
        <div className="wrap">
          {note}
          <TicketHead ticket={ticket} card={card} />
          <StagesSection audit={audit} />
          <InlineReading
            reading={card}
            present={(row) => <HeldBanner card={row} />}
            missing={() => null}
          />

          <div className="cols">
            <div className="main">
              <section className="panel">
                <header>
                  <h2>Brief</h2>
                </header>
                <NoSourceYet brief source={NO_TICKET_BRIEF} />
              </section>

              <section className="panel">
                <header>
                  <h2>Acceptance criteria</h2>
                </header>
                <NoSourceYet brief source={NO_ACCEPTANCE_CRITERIA} />
              </section>

              <WorkTimeline />
              <EvidencePanel audit={audit} />
              <RecordStreamPanel audit={audit} />
              <CommentsPanel audit={audit} select={(events) => events.filter(isComment)} />
            </div>

            <RightRail ticket={ticket} card={card} audit={audit} />
          </div>

          <RecordFoot
            readPath={`/v1/tickets/${shortId(ticket.ticketId)} + /audit + /v1/board`}
            watermark={<AuditNote audit={audit} />}
          />
        </div>
      </main>
    </>
  );
}

function TicketFrame({
  ticketId,
  declared,
}: {
  readonly ticketId: string;
  readonly declared: ReactElement;
}): ReactElement {
  return (
    <>
      <Chrome section="Ticket" back={{ href: "/board", label: "Board" }} />
      <main className="page">
        <div className="wrap">
          <div className="lede">
            <h1>Ticket</h1>
            <p>One ticket in full, read from the instance record.</p>
          </div>
          <section className="panel" style={{ marginTop: "16px" }}>
            <header>
              <h2>{shortId(ticketId)}</h2>
            </header>
            {declared}
          </section>
          <RecordFoot readPath={`/v1/tickets/${shortId(ticketId)}`} />
        </div>
      </main>
    </>
  );
}

/**
 * The line that says how this reader arrived, for the route that chooses the
 * ticket rather than being handed one. It carries the ticket's own stable link,
 * because "the newest ticket" is a moving target and the id is not.
 */
export function ArrivalNote({
  rule,
  ticketId,
}: {
  readonly rule: string;
  readonly ticketId: string;
}): ReactElement {
  return (
    <div className="src-line" style={{ marginTop: "16px" }}>
      <span>{rule}</span>
      <span>
        its stable link is{" "}
        <Link className="mono" href={`/ticket/${encodeURIComponent(ticketId)}`}>
          /ticket/{ticketId}
        </Link>
      </span>
    </div>
  );
}

/**
 * One ticket, read from the instance record. `note` is rendered above the
 * heading when the caller chose the ticket for the reader.
 */
export async function TicketScreen({
  ticketId,
  projectKey,
  note = null,
}: {
  readonly ticketId: string;
  readonly projectKey: string;
  readonly note?: ReactNode;
}): Promise<ReactNode> {
  const [ticket, audit, board] = await Promise.all([
    recordAdapter.ticket(ticketId, projectKey),
    recordAdapter.ticketAudit(ticketId, projectKey),
    recordAdapter.board(projectKey),
  ]);
  const card = cardFor(board, ticketId);

  return (
    <Resolved
      reading={ticket}
      frame={(declared) => <TicketFrame ticketId={ticketId} declared={declared} />}
    >
      {(value) => <TicketBody ticket={value} card={card} audit={audit} note={note} />}
    </Resolved>
  );
}
