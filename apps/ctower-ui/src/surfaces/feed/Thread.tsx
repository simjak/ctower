import type { ReactElement } from "react";
import { clockText, shortId } from "@/read/elapsed";
import type { RecordEvent } from "@/read/interface";
import { EventChip } from "@/surfaces/record/EventChip";
import { byTime, eventHeadline, payloadText } from "@/surfaces/record/events";

function lifecycleFacts(event: RecordEvent): readonly string[] {
  const value: unknown = event.payload.lifecycle_facts;
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function streamClass(event: RecordEvent): string {
  if (event.kind === "workflow.changed") {
    return "fl gate";
  }
  if (event.kind === "proof.changed") {
    return "fl tool";
  }
  return "fl think";
}

/**
 * The thread. Each turn is one appended event: who acted, when, what the
 * record wrote, and the exact payload behind it in a collapsed chip. A
 * lifecycle fact crosses the thread as a system line, the way the approved
 * mockup renders a gate firing.
 */
export function ChatThread({ events }: { readonly events: readonly RecordEvent[] }): ReactElement {
  return (
    <div className="chat">
      {byTime(events).map((event) => {
        const facts = lifecycleFacts(event);
        return (
          <div key={event.eventId}>
            <div className="turn">
              <span className="who">
                <i className="av">RC</i>
              </span>
              <div className="e">
                <div className="hdr">
                  <span className="seat">{event.kind}</span>
                  <span className="crew">principal {shortId(event.actorPrincipalId)}</span>
                  <span className="when">{clockText(event.occurredAt)}</span>
                </div>
                <div className="bub">{eventHeadline(event)}</div>
                <div className="tools">
                  <EventChip event={event} />
                </div>
              </div>
            </div>
            {facts.length === 0 ? null : (
              <div className="sysline">
                <span className="rule" />
                <span className="txt">
                  {clockText(event.occurredAt)} · lifecycle {facts.join(", ")}
                </span>
                <span className="rule" />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** The same events as the timestamped monospace stream, for debugging. */
export function RawStream({ events }: { readonly events: readonly RecordEvent[] }): ReactElement {
  return (
    <div className="stream">
      {byTime(events).map((event) => (
        <div className={streamClass(event)} key={event.eventId}>
          <span className="t">{clockText(event.occurredAt)}</span>
          <span className="k">{event.kind.split(".")[0] ?? event.kind}</span>
          <span className="m">
            {eventHeadline(event)} · {payloadText(event).replace(/\s+/gu, " ")}
          </span>
        </div>
      ))}
    </div>
  );
}
