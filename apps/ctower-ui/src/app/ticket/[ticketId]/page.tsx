import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { Chrome } from "@/frame/Chrome";
import { InlineReading, NoSourceYet, Resolved } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { laneGlyph, StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter } from "@/read/adapter";
import { cardFor } from "@/read/boardProjection";
import { shortId, stampText } from "@/read/elapsed";
import type { BoardCard, Reading, RecordEvent, TicketRecord } from "@/read/interface";
import { mapReading } from "@/read/reading";
import { isComment, isRelation, stagesFrom, workflowRefOf } from "@/surfaces/record/events";
import { CommentsPanel, EvidencePanel, RecordStreamPanel } from "@/surfaces/ticket/RecordPanels";
import type { EventsReading } from "@/surfaces/ticket/RecordPanels";
import { StageStrip } from "@/surfaces/ticket/StageStrip";
import { WorkTimeline } from "@/surfaces/ticket/WorkTimeline";

export const dynamic = "force-dynamic";

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
      ? ({
          state: "absent",
          source: { lands: "#186", what: "a workflow run for this ticket" },
        } as const)
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
      ? ({
          state: "absent",
          source: { lands: "#186", what: "a workflow run for this ticket" },
        } as const)
      : ({ state: "present", value: ref } as const);
  });
  const relations = mapReading(audit, (events) => {
    const found = events.filter(isRelation);
    return found.length === 0
      ? ({
          state: "absent",
          source: { lands: "#186", what: "ticket relations on a read path" },
        } as const)
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
        <NoSourceYet
          source={{
            lands: "#186 / D29",
            what: "the configured label vocabulary and applied labels",
          }}
        />
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
}: {
  readonly ticket: TicketRecord;
  readonly card: Reading<BoardCard>;
  readonly audit: EventsReading;
}): ReactElement {
  return (
    <>
      <Chrome section="Ticket" back={{ href: "/board", label: "Board" }} />
      <main className="page">
        <div className="wrap">
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
                <NoSourceYet
                  brief
                  source={{
                    lands: "#186",
                    what: "a ticket brief beyond the recorded title, priority and source",
                  }}
                />
              </section>

              <section className="panel">
                <header>
                  <h2>Acceptance criteria</h2>
                </header>
                <NoSourceYet
                  brief
                  source={{
                    lands: "#186",
                    what: "criterion text and per-criterion verdicts on a read path",
                  }}
                />
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

export default async function TicketPage({
  params,
}: {
  readonly params: Promise<{ readonly ticketId: string }>;
}): Promise<ReactNode> {
  const { ticketId } = await params;
  const [ticket, audit, board] = await Promise.all([
    recordAdapter.ticket(ticketId),
    recordAdapter.ticketAudit(ticketId),
    recordAdapter.board(),
  ]);
  const card = cardFor(board, ticketId);

  return (
    <Resolved
      reading={ticket}
      frame={(declared) => <TicketFrame ticketId={ticketId} declared={declared} />}
    >
      {(value) => <TicketBody ticket={value} card={card} audit={audit} />}
    </Resolved>
  );
}
