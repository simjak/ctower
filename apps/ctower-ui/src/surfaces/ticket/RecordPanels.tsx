import type { ReactElement, ReactNode } from "react";
import { Resolved } from "@/frame/Declared";
import { StateGlyph } from "@/frame/StateGlyph";
import { clockText, shortId, stampText } from "@/read/elapsed";
import { NO_COMMENTS_HERE, NO_EVENTS_HERE, NO_EVIDENCE_HERE } from "@/read/futureSources";
import type { FutureSource, Reading, RecordEvent } from "@/read/interface";
import { mapReading } from "@/read/reading";
import { EventChip } from "@/surfaces/record/EventChip";
import { byTime, digestOf, eventHeadline, isProof, operationOf } from "@/surfaces/record/events";

export type EventsReading = Reading<readonly RecordEvent[]>;

/** Narrow an audit reading to a non-empty selection, keeping both failure kinds. */
function selection(
  reading: EventsReading,
  choose: (events: readonly RecordEvent[]) => readonly RecordEvent[],
  source: FutureSource
): EventsReading {
  return mapReading(reading, (events): EventsReading => {
    const chosen = byTime(choose(events));
    return chosen.length === 0 ? { state: "absent", source } : { state: "present", value: chosen };
  });
}

function Panel({
  title,
  sub,
  children,
}: {
  readonly title: string;
  readonly sub?: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <section className="panel">
      <header>
        <h2>{title}</h2>
        {sub === undefined ? null : <span className="sub">{sub}</span>}
      </header>
      {children}
    </section>
  );
}

/**
 * Evidence, exactly as the record holds it: one slot per recorded proof
 * operation, carrying its candidate digest and its event hash. A criterion the
 * record does not carry does not get a slot invented for it, and an audit read
 * that did not answer says so rather than showing an empty evidence set.
 */
export function EvidencePanel({ audit }: { readonly audit: EventsReading }): ReactElement {
  const proof = selection(audit, (events) => events.filter(isProof), NO_EVIDENCE_HERE);
  return (
    <Panel title="Evidence">
      <Resolved reading={proof} brief>
        {(events) => (
          <div className="slots">
            {events.map((event) => {
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
      </Resolved>
    </Panel>
  );
}

/**
 * The ticket's own append-only event stream: who acted, under which command, at
 * which position in the hash chain, and the exact payload behind each line.
 */
export function RecordStreamPanel({ audit }: { readonly audit: EventsReading }): ReactElement {
  const stream = selection(audit, (events) => events, NO_EVENTS_HERE);
  return (
    <Panel title="Record stream" sub="append-only">
      <Resolved reading={stream}>
        {(events) => (
          <ul className="tl">
            {events.map((event) => (
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
                    {event.eventHash === null ? null : (
                      <span className="art">{event.eventHash}</span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Resolved>
    </Panel>
  );
}

/** Append-only comments, when the record carries any and the read reached them. */
export function CommentsPanel({
  audit,
  select,
}: {
  readonly audit: EventsReading;
  readonly select: (events: readonly RecordEvent[]) => readonly RecordEvent[];
}): ReactElement {
  const comments = selection(audit, select, NO_COMMENTS_HERE);
  return (
    <Panel title="Comments" sub="append-only">
      <Resolved reading={comments}>
        {(events) => (
          <ul className="cmt">
            {events.map((event) => (
              <li key={event.eventId}>
                <i className="av">RC</i>
                <div className="e">
                  <div className="hdr">
                    <span className="seat">{shortId(event.actorPrincipalId)}</span>
                    <span className="when">{clockText(event.occurredAt)}</span>
                  </div>
                  <p>{event.kind}</p>
                  <div className="sig" style={{ overflowWrap: "anywhere" }}>
                    <span>event {shortId(event.eventId)}</span>
                    {event.eventHash === null ? null : <span>{event.eventHash}</span>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Resolved>
    </Panel>
  );
}
