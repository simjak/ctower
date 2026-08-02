import type { CSSProperties, ReactElement, ReactNode } from "react";
import { StateGlyph } from "./StateGlyph";
import type { ReadFailure } from "@/read/bounded";
import type { FutureSource, Reading } from "@/read/interface";

/**
 * The single boundary where a `Reading` is unwrapped.
 *
 * Everything visible on this surface is either wired to a recorded fact or says
 * on the surface itself that it is not — and it says *which* kind of "is not".
 * A source ctower does not carry yet and a source this read could not reach are
 * opposite claims to an operator, so they get different blocks, different
 * glyphs and different words, and neither is ever silently rendered as the
 * other or as emptiness.
 *
 * Screens call `Resolved`; they never branch on `reading.state` themselves, so
 * no screen can turn a failed read into an empty one. That rule is enforced
 * structurally by `tests/repository/test_browser_network_chokepoint.py`.
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

/**
 * A source that exists and did not answer. This is deliberately loud and
 * deliberately not the block above: it states that the record was not reached,
 * so nothing on this screen may be read as "the record does not hold it".
 */
export function ReadUnavailable({ failure }: { readonly failure: ReadFailure }): ReactElement {
  return (
    <Frame>
      <div
        className="slot"
        style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)" }}
      >
        <StateGlyph name="attn" />
        <div className="e">
          <div className="k">the record was not reached</div>
          <div className="d">
            This source exists — this read did not reach it, so nothing is shown here. Do not read
            this screen as evidence that the record is empty; it is evidence that the read failed.
          </div>
          <div className="f" style={{ overflowWrap: "anywhere" }}>
            <span className="req">{failure.reason}</span>
            <span>{failure.failureClass} failure</span>
            <span>
              {failure.attempts.toString()} bounded{" "}
              {failure.attempts === 1 ? "attempt" : "attempts"} over {failure.elapsedMs.toString()}
              ms
            </span>
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
      return <ReadUnavailable failure={reading.failure} />;
  }
}

function identity(declared: ReactElement): ReactNode {
  return declared;
}

/**
 * Unwrap a reading, or render its declared state. This is the only way a screen
 * reaches a value, so an unavailable read cannot reach a surface as content.
 *
 * `frame` places the declared block inside whatever chrome the screen needs
 * when there is no value to render; it never sees which state fired.
 */
export function Resolved<T>({
  reading,
  children,
  frame = identity,
}: {
  readonly reading: Reading<T>;
  readonly children: (value: T) => ReactNode;
  readonly frame?: (declared: ReactElement) => ReactNode;
}): ReactNode {
  switch (reading.state) {
    case "present":
      return children(reading.value);
    case "absent":
      return frame(<NoSourceYet source={reading.source} />);
    case "unavailable":
      return frame(<ReadUnavailable failure={reading.failure} />);
  }
}

const NOT_REACHED = {
  borderColor: "var(--warn-line)",
  background: "var(--warn-bg)",
  color: "var(--warn)",
} as const;

/**
 * The compact boundary, for a reading that belongs inside a row rather than in
 * a panel of its own — a board card's source and age, say.
 *
 * `missing` still receives the two kinds separately: `not recorded` and
 * `not reached` are different claims and are never rendered as each other or as
 * a bare dash. The caller cannot substitute a default, because it never gets a
 * value to default from.
 */
export function InlineReading<T>({
  reading,
  present,
  missing,
}: {
  readonly reading: Reading<T>;
  readonly present: (value: T) => ReactNode;
  readonly missing: (label: string, detail: string, tone: CSSProperties) => ReactNode;
}): ReactNode {
  switch (reading.state) {
    case "present":
      return present(reading.value);
    case "absent":
      return missing("not recorded", `lands with ${reading.source.lands}`, {});
    case "unavailable":
      return missing("not reached", reading.failure.reason, NOT_REACHED);
  }
}
