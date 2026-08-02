import Link from "next/link";
import type { ReactElement } from "react";
import { laneGlyph, StateGlyph } from "@/frame/StateGlyph";
import { elapsedSince, shortId } from "@/read/elapsed";
import type { BoardEntry } from "@/read/interface";

function priorityClass(priority: string): string {
  return `pri ${priority.toLowerCase()}`;
}

/**
 * One board card. Every line is a fact `/v1/board` or `/v1/tickets/{id}`
 * returned; the change reference reads `PR —` when `delivery_facts` is the
 * empty set the record actually holds, exactly as the mockup renders an
 * absent change reference.
 */
export function LaneCard({
  entry,
  now,
}: {
  readonly entry: BoardEntry;
  readonly now: number;
}): ReactElement {
  const { card, ticket } = entry;
  const change = card.deliveryFacts[0];
  const age = ticket === null ? null : elapsedSince(ticket.createdAt, now);

  return (
    <Link className="card" href={`/ticket/${encodeURIComponent(card.ticketId)}`}>
      <div className="card-top">
        <span className="tid">{shortId(card.ticketId)}</span>
        <span className={priorityClass(card.priority)}>{card.priority}</span>
        <span className="right">
          <span className={change === undefined ? "pr" : "pr live"}>{change ?? "PR —"}</span>
        </span>
      </div>
      <h3 className="card-title">
        <StateGlyph name={laneGlyph(card.lane, card.blockerReason !== null)} />
        {card.title}
      </h3>
      {card.blockerReason === null ? null : (
        <div className="card-note held">held · {card.blockerReason}</div>
      )}
      {card.risk === null ? null : <div className="card-note">risk · {card.risk}</div>}
      {card.stageLabel === null ? null : (
        <div className="card-note">
          stage {card.stageLabel}
          {card.activityClass === null ? "" : ` · ${card.activityClass}`}
        </div>
      )}
      <div className="card-foot">
        {ticket === null ? null : <span className="chip">{ticket.source.kind}</span>}
        <span className="seat">
          <span className="nm">custodian {shortId(card.custodianId)}</span>
        </span>
        <span className="dur">{age === null ? "age —" : `age ${age}`}</span>
      </div>
    </Link>
  );
}
