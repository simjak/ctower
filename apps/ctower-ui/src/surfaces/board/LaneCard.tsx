import Link from "next/link";
import type { ReactElement } from "react";
import { InlineReading } from "@/frame/Declared";
import { laneGlyph, StateGlyph } from "@/frame/StateGlyph";
import { elapsedSince, shortId } from "@/read/elapsed";
import { tenantChipFor } from "@/read/boardProjection";
import type { BoardCard, BoardEntry } from "@/read/interface";

function priorityClass(priority: string): string {
  return `pri ${priority.toLowerCase()}`;
}

/**
 * The tenant chip, when the caller asks for it (gh#319's cross-project
 * portfolio view — the normal per-project rail never sets `showTenant`,
 * because every card on it is already known to be this project's own read).
 * `known`/`unknown` both render: an unattributed ticket says so, the `title`
 * carries why, rather than the row silently dropping the fact. The
 * `known`/`unknown` union itself is narrowed in `read/boardProjection.ts`
 * (`tenantChipFor`), not here — a surface may not inspect a fact's own
 * discriminant, the same rule `frame/Declared.tsx` holds for a `Reading`.
 */
function tenantChip(card: BoardCard): ReactElement {
  const facts = tenantChipFor(card.tenantDisplayIdentity);
  return (
    <span className="chip" title={facts.title}>
      {facts.label}
    </span>
  );
}

/**
 * One board card. Every line is a fact `/v1/board` or `/v1/tickets/{id}`
 * returned; the change reference reads `PR —` when `delivery_facts` is the
 * empty set the record actually holds, exactly as the mockup renders an absent
 * change reference.
 *
 * The source and the age come from a second read that can fail on its own. When
 * it does the card says `source not reached` and `age not reached` in the warn
 * treatment rather than dropping to a dash — a dash there would claim the
 * record holds no source.
 */
export function LaneCard({
  entry,
  now,
  showTenant,
}: {
  readonly entry: BoardEntry;
  readonly now: number;
  /** Render the tenant chip. Defaults to unset (the per-project rail omits it). */
  readonly showTenant?: boolean;
}): ReactElement {
  const { card, ticket } = entry;
  const change = card.deliveryFacts[0];
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
        <span className={priorityClass(card.priority)}>{card.priority}</span>
        {/* the audit found a dash chip on all thirteen cards: a change
            reference the record does not carry is simply not shown */}
        {change === undefined ? null : (
          <span className="right">
            <span className="pr live">{change}</span>
          </span>
        )}
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
        {showTenant === true ? tenantChip(card) : null}
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
