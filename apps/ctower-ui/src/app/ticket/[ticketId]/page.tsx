import Link from "next/link";
import type { ReactElement } from "react";
import { Chrome } from "@/frame/Chrome";
import { DeclaredState, NoSourceYet } from "@/frame/Declared";
import { RecordFoot } from "@/frame/RecordFoot";
import { laneGlyph, StateGlyph } from "@/frame/StateGlyph";
import { recordAdapter } from "@/read/adapter";
import { clockText, shortId, stampText } from "@/read/elapsed";
import type { BoardCard, RecordEvent, TicketRecord } from "@/read/interface";
import { isComment, isRelation, stagesFrom, workflowRefOf } from "@/surfaces/record/events";
import { EvidencePanel, RecordStreamPanel } from "@/surfaces/ticket/RecordPanels";
import { StageStrip } from "@/surfaces/ticket/StageStrip";
import { WorkTimeline } from "@/surfaces/ticket/WorkTimeline";

export const dynamic = "force-dynamic";

function TicketHead({
  ticket,
  card,
}: {
  readonly ticket: TicketRecord;
  readonly card: BoardCard | null;
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
        <StateGlyph
          name={card === null ? "open" : laneGlyph(card.lane, card.blockerReason !== null)}
        />
        {ticket.title}
      </h1>
      <div className="tmeta">
        <span className={`pri ${ticket.priority.toLowerCase()}`}>{ticket.priority}</span>
        {card === null ? null : <span className="chip">lane {card.lane}</span>}
        {card?.stageLabel === undefined || card.stageLabel === null ? null : (
          <span className="chip">stage {card.stageLabel}</span>
        )}
        <span className="chip">durability {ticket.durabilityState}</span>
        <span className="chip">version {ticket.version.toString()}</span>
      </div>
      <div className="custody">
        <span className="k">custodian</span>
        <span className="mono">{ticket.custodianId}</span>
        <span className="k">created</span>
        <span className="mono">{stampText(ticket.createdAt)}</span>
        {card?.assigneeId === undefined || card.assigneeId === null ? null : (
          <>
            <span className="k">assignee</span>
            <span className="mono">{card.assigneeId}</span>
          </>
        )}
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

function RightRail({
  ticket,
  card,
  events,
}: {
  readonly ticket: TicketRecord;
  readonly card: BoardCard | null;
  readonly events: readonly RecordEvent[];
}): ReactElement {
  const relations = events.filter(isRelation);
  const workflow = workflowRefOf(events);
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
            <span className="v">{workflow ?? "none recorded"}</span>
          </li>
          <li>
            <span className="k">durability</span>
            <span className="v">{ticket.durabilityState}</span>
          </li>
          <li>
            <span className="k">board</span>
            <Link className="v" href="/board">
              back to the lanes
            </Link>
          </li>
          {card === null ? null : (
            <li>
              <span className="k">delivery</span>
              <span className="v">
                {card.deliveryFacts.length === 0
                  ? "no change reference recorded"
                  : card.deliveryFacts.join(" · ")}
              </span>
            </li>
          )}
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
        {relations.length === 0 ? (
          <NoSourceYet source={{ lands: "#186", what: "ticket relations on a read path" }} />
        ) : (
          <ul className="links">
            {relations.map((event) => (
              <li key={event.eventId}>
                <span className="k">{clockText(event.occurredAt)}</span>
                <span className="v">{event.kind}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}

export default async function TicketPage({
  params,
}: {
  readonly params: Promise<{ readonly ticketId: string }>;
}): Promise<ReactElement> {
  const { ticketId } = await params;
  const [ticket, audit, board] = await Promise.all([
    recordAdapter.ticket(ticketId),
    recordAdapter.ticketAudit(ticketId),
    recordAdapter.board(),
  ]);

  if (ticket.state !== "present") {
    return (
      <>
        <Chrome section="Ticket" back />
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
              <DeclaredState reading={ticket} />
            </section>
            <RecordFoot readPath={`/v1/tickets/${ticketId}`} />
          </div>
        </main>
      </>
    );
  }

  const events = audit.state === "present" ? audit.value : [];
  const card =
    board.state === "present"
      ? (board.value.entries.find((entry) => entry.card.ticketId === ticketId)?.card ?? null)
      : null;
  const stages = stagesFrom(events);
  const comments = events.filter(isComment);

  return (
    <>
      <Chrome section="Ticket" back />
      <main className="page">
        <div className="wrap">
          <TicketHead ticket={ticket.value} card={card} />
          {stages.length === 0 ? (
            <section className="panel" style={{ marginTop: "18px" }}>
              <header>
                <h2>Stages</h2>
              </header>
              <NoSourceYet
                source={{ lands: "#186", what: "a workflow run for this ticket" }}
                title="no workflow started"
              />
            </section>
          ) : (
            <StageStrip stages={stages} />
          )}
          {card === null ? null : <HeldBanner card={card} />}

          <div className="cols">
            <div className="main">
              <section className="panel">
                <header>
                  <h2>Brief</h2>
                </header>
                <NoSourceYet
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
                  source={{
                    lands: "#186",
                    what: "criterion text and per-criterion verdicts on a read path",
                  }}
                />
              </section>

              <WorkTimeline />
              <EvidencePanel events={events} />
              <RecordStreamPanel events={events} />

              <section className="panel">
                <header>
                  <h2>Comments</h2>
                  <span className="sub">append-only</span>
                </header>
                {comments.length === 0 ? (
                  <NoSourceYet source={{ lands: "#186", what: "ticket comments on a read path" }} />
                ) : (
                  <ul className="cmt">
                    {comments.map((event) => (
                      <li key={event.eventId}>
                        <i className="av">RC</i>
                        <div className="e">
                          <div className="hdr">
                            <span className="seat">{shortId(event.actorPrincipalId)}</span>
                            <span className="when">{clockText(event.occurredAt)}</span>
                          </div>
                          <p>{event.kind}</p>
                          <div className="sig">
                            <span>event {shortId(event.eventId)}</span>
                            {event.eventHash === null ? null : <span>{event.eventHash}</span>}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            <RightRail ticket={ticket.value} card={card} events={events} />
          </div>

          <RecordFoot
            readPath={`/v1/tickets/${shortId(ticketId)} + /audit + /v1/board`}
            watermark={
              audit.state === "present"
                ? `${events.length.toString()} appended events`
                : "audit read unavailable"
            }
          />
        </div>
      </main>
    </>
  );
}
