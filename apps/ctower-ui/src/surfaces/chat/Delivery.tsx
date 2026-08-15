import type { ReactElement } from "react";
import { clockText } from "@/read/elapsed";
import type { InboxMessageDelivery } from "@/read/interface";

/**
 * How far a message got, drawn the way the approved chat surface draws it.
 *
 * Three progressive dots: the record accepted it, the recipient's side accepted
 * it, the recipient opened the thread. Each is a recorded event with its own
 * id, so the mark is never inferred — a message with no read event draws two
 * dots and says `read not recorded`, rather than borrowing the thread's read
 * cursor to fill the third.
 *
 * The dots are the de-texted element and the exact timestamps are the hover,
 * which is what the approved surface does: six pixels carry the state, and the
 * reader who wants the times has them without every row spending a line on
 * them.
 */

const FILLED: Readonly<Record<InboxMessageDelivery["state"], number>> = {
  sent: 1,
  delivered: 2,
  read: 3,
};

/** `sent 01:02:43 · delivered 01:02:44 · read 01:09:11` — the approved wording. */
export function deliveryTitle(delivery: InboxMessageDelivery, sentAt: string): string {
  return [
    `sent ${clockText(sentAt)}`,
    delivery.deliveredAt === null
      ? "delivered not recorded"
      : `delivered ${clockText(delivery.deliveredAt)}`,
    delivery.readAt === null ? "read not recorded" : `read ${clockText(delivery.readAt)}`,
  ].join(" · ");
}

function Dots({ filled }: { readonly filled: number }): ReactElement {
  return (
    <>
      {[0, 1, 2].map((index) => (
        <i className={index < filled ? "on" : ""} key={index} />
      ))}
    </>
  );
}

/** The mark on one message. */
export function DeliveryMark({
  delivery,
  sentAt,
}: {
  readonly delivery: InboxMessageDelivery;
  readonly sentAt: string;
}): ReactElement {
  return (
    <div className="audit">
      <span className="fx" title={deliveryTitle(delivery, sentAt)}>
        <Dots filled={FILLED[delivery.state]} />
      </span>
    </div>
  );
}

const LEGEND: readonly (readonly [InboxMessageDelivery["state"], string])[] = [
  ["sent", "the record accepted it"],
  ["delivered", "the recipient's side accepted it"],
  ["read", "the recipient opened the thread"],
];

/** The one legend, in the thread head, that teaches the three marks below it. */
export function DeliveryLegend(): ReactElement {
  return (
    <span className="cw-legend">
      {LEGEND.map(([state, what]) => (
        <span className="cw-legend-entry" key={state}>
          <span className="fx" title={`${state} — ${what}`}>
            <Dots filled={FILLED[state]} />
          </span>
          {state}
        </span>
      ))}
    </span>
  );
}
