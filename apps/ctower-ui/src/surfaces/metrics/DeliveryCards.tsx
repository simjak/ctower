import type { ReactElement } from "react";
import type { DeliveryMeasure } from "@/read/interface";

/**
 * The delivery cards, in the approved metrics idiom.
 *
 * A measure whose record does not exist gets the mockup's own `na` treatment —
 * the words where the number would be, `no target yet`, and `src: —` — plus the
 * work that would land it. This is the page where a wrong number would be
 * believed, so a card either states a measurement and names the derivation it
 * came from, or it states that there is nothing to measure. There is no third
 * rendering, and in particular there is no zero standing in for absence.
 *
 * The de-texting amendment moved the measure's `note` off the card: four cards
 * on one screenful each carried two or three sentences of it, repeated once per
 * project tab. The card still says everything it said — the value or
 * `not recorded`, the target, the work that would land it, and the derivation
 * it is read from — and the sentence behind that derivation is the card's hover.
 */
function Card({ measure }: { readonly measure: DeliveryMeasure }): ReactElement {
  const missing = measure.value === null;
  return (
    <div className={missing ? "mtcard na" : "mtcard"}>
      <div className="k">{measure.title}</div>
      <div className="v">
        {missing ? (
          "not recorded"
        ) : (
          <>
            {measure.value}
            {measure.unit === null ? null : <u>{measure.unit}</u>}
          </>
        )}
      </div>
      {missing ? (
        <div className="mtnospark">
          {measure.lands === undefined ? "no record to draw" : `lands with ${measure.lands}`}
        </div>
      ) : null}
      <span className={missing ? "mttgt na" : "mttgt ok"}>{measure.target}</span>
      <div className="src" title={measure.note}>
        {measure.source}
      </div>
    </div>
  );
}

export function DeliveryCards({
  measures,
}: {
  readonly measures: readonly DeliveryMeasure[];
}): ReactElement {
  return (
    <>
      {measures.map((measure) => (
        <Card key={measure.title} measure={measure} />
      ))}
    </>
  );
}
