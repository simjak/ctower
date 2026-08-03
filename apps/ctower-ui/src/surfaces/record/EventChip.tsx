import type { ReactElement } from "react";
import { payloadText } from "./events";
import type { RecordEvent } from "@/read/interface";

/**
 * One recorded event as the shared collapsed chip. The summary is the event's
 * own kind and command; expanding shows the exact payload the record holds,
 * unedited — this is the disclosure idiom the feed and the ticket both use, so
 * there is only one expander in the product.
 */
export function EventChip({ event }: { readonly event: RecordEvent }): ReactElement {
  return (
    <details className="toolchip">
      <summary>
        <span className="kind">{event.kind}</span>
        <span className="arg">command {event.commandId}</span>
      </summary>
      <div className="out">{payloadText(event)}</div>
    </details>
  );
}
