import Link from "next/link";
import type { ReactElement } from "react";
import { InlineReading } from "@/frame/Declared";
import { laneGlyph, StateGlyph } from "@/frame/StateGlyph";
import { elapsedSince, shortId } from "@/read/elapsed";
import { boardCardContextFor } from "@/read/boardProjection";
import type { BoardContextValue } from "@/read/boardProjection";
import type { BoardEntry } from "@/read/interface";
import { laneTitleOf } from "./lanes";

function priorityClass(priority: string): string {
  return `pri ${priority.toLowerCase()}`;
}

function ContextRow({
  label,
  values,
  attention = false,
}: {
  readonly label: string;
  readonly values: readonly BoardContextValue[];
  readonly attention?: boolean;
}): ReactElement {
  return (
    <div className={attention ? "context-row attn" : "context-row"}>
      <span className="context-key">{label}</span>
      <span className="context-values">
        {values.map((fact, index) => (
          <span
            className="context-value"
            key={`${fact.value}-${index.toString()}`}
            title={fact.detail}
          >
            {fact.value}
          </span>
        ))}
      </span>
    </div>
  );
}

/**
 * One board card. Every line is a fact `/v1/board` or `/v1/tickets/{id}`
 * returned. The five context rows are always present because their contract
 * distinguishes an empty/absent/unknown value from omission.
 *
 * The source and the age come from a second read that can fail on its own. When
 * it does the card says `source not reached` and `age not reached` in the warn
 * treatment rather than dropping to a dash — a dash there would claim the
 * record holds no source.
 */
export function LaneCard({
  entry,
  now,
}: {
  readonly entry: BoardEntry;
  readonly now: number;
}): ReactElement {
  const { card, ticket } = entry;
  const context = boardCardContextFor(card);
  // F-001a: the seat name when the record resolves one, and an honest
  // "seat unnamed" otherwise — never a ULID truncated to a single character by
  // the column, which is what the audit found
  const custodian = (
    <span className="seat" title={`custodian principal ${card.custodianId}`}>
      <span className="nm">{card.custodianName ?? "seat unnamed"}</span>
    </span>
  );

  return (
    <Link className="card" href={`/ticket/${encodeURIComponent(card.ticketId)}`}>
      <div className="card-top">
        <span className="tid">{shortId(card.ticketId)}</span>
        {/* the lane used to be the column this card sat in. The list is flat now,
            so the card carries its own recorded lane rather than inheriting it
            from where it was drawn */}
        <span className="chip" title={`board lane ${card.lane}`}>
          {laneTitleOf(card.lane)}
        </span>
        <span className="right">
          <span className={priorityClass(card.priority)}>{card.priority}</span>
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
      <div className="card-context" aria-label="Board card context">
        <ContextRow label="Tenant" values={[context.tenant]} />
        <ContextRow label="Changes" values={context.changes} />
        <ContextRow label="Labels" values={context.labels} />
        <ContextRow
          label="Human waiting"
          values={[context.humanWaiting]}
          attention={context.humanWaiting.attention}
        />
        <ContextRow
          label="Delivery surface"
          values={[
            context.deliverySurface,
            ...(context.deliverySurface.details ?? []).map((value) => ({ value })),
          ]}
        />
      </div>
      <div className="card-foot">
        <InlineReading
          reading={ticket}
          present={(value) => (
            <>
              {/* the issue the ticket was raised from, when the record
                  addresses one. It is a chip and not an anchor because the whole
                  card is already one link, and an anchor inside an anchor is not
                  a control a browser can render — the ticket screen carries the
                  real link one click away */}
              {value.source.issue === null ? (
                <span className="chip">{value.source.kind}</span>
              ) : (
                <span className="chip" title={`${value.source.kind} · ${value.source.issue.url}`}>
                  {value.source.issue.label}
                </span>
              )}
              {custodian}
              <span className="dur">age {elapsedSince(value.createdAt, now) ?? "unparsable"}</span>
            </>
          )}
          missing={(label, detail, tone) => (
            <>
              <span className="chip" style={tone} title={detail}>
                source {label}
              </span>
              {custodian}
              <span className="dur" style={tone} title={detail}>
                age {label}
              </span>
            </>
          )}
        />
      </div>
    </Link>
  );
}
