import type { ReactElement } from "react";
import { NoSourceYet } from "@/frame/Declared";
import { StateGlyph } from "@/frame/StateGlyph";
import { clockText, shortId, stampText } from "@/read/elapsed";
import type { RecordEvent } from "@/read/interface";
import { EventChip } from "@/surfaces/record/EventChip";
import { byTime, digestOf, eventHeadline, isProof, operationOf } from "@/surfaces/record/events";

/**
 * Evidence, exactly as the record holds it: one slot per recorded proof
 * operation, carrying its candidate digest and its event hash. A criterion the
 * record does not carry does not get a slot invented for it.
 */
export function EvidencePanel({
  events,
}: {
  readonly events: readonly RecordEvent[];
}): ReactElement {
  const proof = byTime(events.filter(isProof));
  return (
    <section className="panel">
      <header>
        <h2>Evidence</h2>
        <span className="sub">
          {proof.length.toString()} recorded proof {proof.length === 1 ? "operation" : "operations"}
        </span>
      </header>
      {proof.length === 0 ? (
        <NoSourceYet
          source={{
            lands: "#186",
            what: "typed evidence slots and their filled / required coverage on a read path",
          }}
        />
      ) : (
        <div className="slots">
          {proof.map((event) => {
            const digest = digestOf(event);
            return (
              <div className="slot" key={event.eventId}>
                <StateGlyph name="done" />
                <div className="e">
                  <div className="k">{operationOf(event) ?? event.kind}</div>
                  <div className="d">
                    Recorded at {stampText(event.occurredAt)} by principal{" "}
                    {shortId(event.actorPrincipalId)}.
                  </div>
                  <div className="f" style={{ overflowWrap: "anywhere" }}>
                    {digest === null ? null : <span>{digest}</span>}
                    {event.eventHash === null ? null : <span>{event.eventHash}</span>}
                    {event.recordPosition === null ? null : (
                      <span>record position {event.recordPosition.toString()}</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

/**
 * The ticket's own append-only event stream. This is what ctower records
 * today: who acted, under which command, at which position in the hash chain,
 * and the exact payload behind each line.
 */
export function RecordStreamPanel({
  events,
}: {
  readonly events: readonly RecordEvent[];
}): ReactElement {
  const ordered = byTime(events);
  return (
    <section className="panel">
      <header>
        <h2>Record stream</h2>
        <span className="sub">
          {ordered.length.toString()} appended {ordered.length === 1 ? "event" : "events"} ·
          append-only
        </span>
      </header>
      <ul className="tl">
        {ordered.map((event) => (
          <li key={event.eventId}>
            <span className="who">
              <i className="av">RC</i>
            </span>
            <div className="e">
              <div className="hdr">
                <span className="seat">{event.kind}</span>
                <span className="crew">principal {shortId(event.actorPrincipalId)}</span>
                <span className="when">{clockText(event.occurredAt)}</span>
              </div>
              <div className="did">{eventHeadline(event)}</div>
              <div className="tools">
                <EventChip event={event} />
              </div>
              <div className="arts" style={{ overflowWrap: "anywhere" }}>
                <span className="art">event {shortId(event.eventId)}</span>
                {event.streamId === null ? null : <span className="art">{event.streamId}</span>}
                {event.eventHash === null ? null : <span className="art">{event.eventHash}</span>}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
