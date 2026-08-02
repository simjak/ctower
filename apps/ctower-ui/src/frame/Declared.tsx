import type { ReactElement } from "react";
import { StateGlyph } from "./StateGlyph";
import type { FutureSource, Reading } from "@/read/interface";

/**
 * Everything visible on this surface is either wired to a recorded fact or
 * says on the surface itself that it is not. These two blocks are the second
 * case, drawn in the same unfilled-slot idiom the ticket already uses for a
 * required-but-empty evidence slot — no new colour, no banner.
 */

function Frame({ children }: { readonly children: ReactElement }): ReactElement {
  return (
    <div className="slots" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
      {children}
    </div>
  );
}

export function NoSourceYet({
  source,
  title = "no data source yet",
}: {
  readonly source: FutureSource;
  readonly title?: string;
}): ReactElement {
  return (
    <Frame>
      <div className="slot open">
        <StateGlyph name="open" />
        <div className="e">
          <div className="k">{title}</div>
          <div className="d">
            ctower does not record {source.what}. The layout above is the approved shape this screen
            takes the moment that record exists; nothing below it is filled in from a guess.
          </div>
          <div className="f">
            <span className="req">lands with {source.lands}</span>
            <span>read-only v1</span>
          </div>
        </div>
      </div>
    </Frame>
  );
}

export function ReadUnavailable({ reason }: { readonly reason: string }): ReactElement {
  return (
    <Frame>
      <div className="slot open">
        <StateGlyph name="attn" />
        <div className="e">
          <div className="k">the record did not answer</div>
          <div className="d">
            A source exists for this screen, but this read did not complete, so nothing is shown
            rather than something stale.
          </div>
          <div className="f">
            <span className="req">{reason}</span>
          </div>
        </div>
      </div>
    </Frame>
  );
}

/** Render the one non-present state of a reading, or `null` when it is present. */
export function DeclaredState<T>({
  reading,
}: {
  readonly reading: Reading<T>;
}): ReactElement | null {
  switch (reading.state) {
    case "present":
      return null;
    case "absent":
      return <NoSourceYet source={reading.source} />;
    case "unavailable":
      return <ReadUnavailable reason={reading.reason} />;
  }
}
