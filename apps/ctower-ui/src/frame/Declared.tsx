import type { CSSProperties, ReactElement, ReactNode } from "react";
import { StateGlyph } from "./StateGlyph";
import { landsText } from "@/read/futureSources";
import type { ReadFailure } from "@/read/bounded";
import type { FutureSource, Reading } from "@/read/interface";
import type { Known } from "@/read/sources/maybe";

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

/**
 * The line that cites the work landing a missing capability — or says plainly
 * that nothing is filed.
 *
 * Round-3 QA (#241) found nine panels citing one issue that covered none of
 * them. A citation now carries the sentence saying how that item covers this
 * exact fact, so the claim is inspectable on the surface itself; an uncited
 * capability says so instead of borrowing the nearest number.
 */
function Lands({ source }: { readonly source: FutureSource }): ReactElement | null {
  if (source.absence === "silence") {
    return null;
  }
  return (
    <span className="req" title={source.why ?? undefined}>
      {landsText(source)}
    </span>
  );
}

/**
 * The design audit found this block's full sentence repeating verbatim eight
 * times on one page: honest, and unreadable by the third repeat. The rule for
 * a page is now say-it-once — the first block on a screen carries the whole
 * explanation, every later one carries the fact and the source alone. Callers
 * mark the later ones with `brief`.
 *
 * The block says which of the two absences it is. "ctower does not record this"
 * and "the record answered and holds none for this ticket" are different claims,
 * and the second needs no roadmap pointer at all — the fact arrives the moment
 * someone appends one.
 */
export function NoSourceYet({
  source,
  title,
  brief = false,
}: {
  readonly source: FutureSource;
  readonly title?: string;
  readonly brief?: boolean;
}): ReactElement {
  const silent = source.absence === "silence";
  const heading = title ?? (silent ? "the record holds none here" : "no data source yet");
  const said = silent
    ? `The record answered and holds no ${source.what}.`
    : `ctower does not record ${source.what}.`;
  const whole = silent
    ? " The layout above is the shape this panel takes the moment one is appended; nothing below it is filled in from a guess."
    : " The layout above is the approved shape this screen takes the moment that record exists; nothing below it is filled in from a guess.";
  return (
    <Frame>
      <div className="slot open">
        <StateGlyph name="open" />
        <div className="e">
          <div className="k">{heading}</div>
          <div className="d">{brief ? said : `${said}${whole}`}</div>
          <div className="f">
            <Lands source={source} />
            {brief ? null : <span>read-only v1</span>}
          </div>
        </div>
      </div>
    </Frame>
  );
}

/**
 * Statuses that mean *refused*, not *unreachable*.
 *
 * "We could not reach it" and "we are not allowed to look" are different things
 * to tell an operator, and only one of them is worth retrying. The status comes
 * from the typed failure rather than from matching prose in `reason`.
 */
const REFUSED_STATUS = new Set([401, 403]);

/**
 * A source that exists and did not answer. This is deliberately loud and
 * deliberately not the block above: it states that the record was not reached,
 * so nothing on this screen may be read as "the record does not hold it".
 *
 * When the instance *refused* — 401 or 403 — the block says so in those words
 * and names what unblocks it, because an empty board and a board the reader is
 * not authorized to see must never look alike. Issuing a credential for a
 * project is operator-only under D30, so this is not a state the surface can
 * retry its way out of, and it does not pretend otherwise.
 */
export function ReadUnavailable({
  failure,
  subject = null,
}: {
  readonly failure: ReadFailure;
  /** What the read was for, when the caller can name it: `project manibo`. */
  readonly subject?: string | null;
}): ReactElement {
  const refused = failure.status !== null && REFUSED_STATUS.has(failure.status);
  const named = subject ?? "this read";
  return (
    <Frame>
      <div
        className="slot"
        style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)" }}
      >
        <StateGlyph name="attn" />
        <div className="e">
          <div className="k">
            {refused ? `not allowed to read ${named}` : "the record was not reached"}
          </div>
          <div className="d">
            {refused ? (
              <>
                The instance answered {String(failure.status)}: the credential this surface holds is
                not authorized for {named}. This is a refusal, not an outage and not an empty board
                — there may be work here that you cannot see from this surface. Issuing a scoped
                credential is operator-only, so it unblocks when the operator issues one; no amount
                of retrying reaches it.
              </>
            ) : (
              <>
                This source exists — this read did not reach it, so nothing is shown here. Do not
                read this screen as evidence that the record is empty; it is evidence that the read
                failed.
              </>
            )}
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
  brief = false,
  subject = null,
}: {
  readonly reading: Reading<T>;
  readonly children: (value: T) => ReactNode;
  readonly frame?: (declared: ReactElement) => ReactNode;
  /** A later block on a page whose first block already carried the sentence. */
  readonly brief?: boolean;
  /** What this read was for, so a refusal can name it. */
  readonly subject?: string | null;
}): ReactNode {
  switch (reading.state) {
    case "present":
      return children(reading.value);
    case "absent":
      return frame(<NoSourceYet source={reading.source} brief={brief} />);
    case "unavailable":
      return frame(<ReadUnavailable failure={reading.failure} subject={subject} />);
  }
}

const NOT_REACHED = {
  borderColor: "var(--warn-line)",
  background: "var(--warn-bg)",
  color: "var(--warn)",
} as const;

/** The same honesty as `Lands`, folded into one line for an inline hover. */
function detailOf(source: FutureSource): string {
  if (source.absence === "silence") {
    return `the record answered and holds no ${source.what}`;
  }
  return source.why === null
    ? `ctower does not record ${source.what} · ${landsText(source)}`
    : `${source.why} · ${landsText(source)}`;
}

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
      return missing("not recorded", detailOf(reading.source), {});
    case "unavailable":
      return missing("not reached", reading.failure.reason, NOT_REACHED);
  }
}

/**
 * One sub-read rendered honestly: a value, an answered emptiness, or a read
 * that did not happen. The third is never drawn as the second.
 */
export function KnownValue({
  value,
  render = (text: string): ReactNode => text,
}: {
  readonly value: Known<string>;
  readonly render?: (text: string) => ReactNode;
}): ReactNode {
  switch (value.known) {
    case "value":
      return render(value.value);
    case "none":
      return <span title={value.why}>{value.why}</span>;
    case "unread":
      return (
        <span style={NOT_REACHED} title={value.reason}>
          not reached
        </span>
      );
  }
}
