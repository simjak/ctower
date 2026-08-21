import type { CSSProperties, ReactElement, ReactNode } from "react";
import { StateGlyph } from "./StateGlyph";
import { landsText } from "@/read/futureSources";
import type { ReadFailure } from "@/read/bounded";
import type { FutureSource, Reading, UnreachedScope } from "@/read/interface";
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
 * A fact this surface has nothing to show for, said without a sentence.
 *
 * The design audit found this block's full explanation repeating verbatim eight
 * times on one page — honest, and unreadable by the third repeat — so a `brief`
 * flag dropped the tail on every block after the first. The operator's
 * de-texting amendment finishes the job: the paragraph is gone entirely, and the
 * three things a reader needs are three elements. The glyph and the heading say
 * *which kind of nothing* it is, the subject line is the recorded fact itself
 * rather than a sentence about it, and the citation is a chip.
 *
 * The two absences stay different claims with different headings. "ctower does
 * not record this" and "the record answered and holds none of it" are opposite
 * things to tell an operator, and only the first has anything to wait for.
 *
 * `brief` is kept because callers pass it, but there is no longer a longer
 * form for it to suppress — every block is now the short one.
 */
export function NoSourceYet({
  source,
  title,
}: {
  readonly source: FutureSource;
  readonly title?: string;
  /** Retained for callers; every block is now the brief form. */
  readonly brief?: boolean;
}): ReactElement {
  const silent = source.absence === "silence";
  const heading = title ?? (silent ? "the record holds none" : "not recorded");
  return (
    <Frame>
      <div className="slot open">
        <StateGlyph name="open" />
        <div className="e">
          <div className="k">{heading}</div>
          <div className="d">{source.what}</div>
          <div className="f">
            <Lands source={source} />
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
 * The one thing a reader can act on when the instance refuses, carried by the
 * chip's hover rather than by a paragraph: this is not an outage and not an
 * empty board, and no amount of retrying reaches it.
 */
const REFUSAL_HINT =
  "a refusal, not an outage and not an empty board — there may be work here this surface's credential cannot see, and issuing a scoped one is operator-only";

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
          <div className="k">{refused ? "not allowed to read" : "not reached"}</div>
          <div className="d">{named}</div>
          <div className="f" style={{ overflowWrap: "anywhere" }}>
            {failure.status === null ? null : (
              <span className="req">{failure.status.toString()}</span>
            )}
            <span className="req">{failure.reason}</span>
            <span>{failure.failureClass}</span>
            <span>
              {failure.attempts.toString()} {failure.attempts === 1 ? "attempt" : "attempts"} ·{" "}
              {failure.elapsedMs.toString()}ms
            </span>
            {refused ? <span title={REFUSAL_HINT}>operator-issued credential</span> : null}
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
  return value.known === "value" ? render(value.value) : <KnownAbsence value={value} />;
}

/**
 * The same two non-value states, for a sub-read whose value is not text — a
 * project's lane counts, say. The caller renders the value case itself and
 * hands the absence here, so "the record holds none" and "this read failed"
 * keep one wording and one treatment across the app instead of being
 * re-authored per screen.
 */
export function KnownAbsence({ value }: { readonly value: Known<unknown> }): ReactNode {
  switch (value.known) {
    case "value":
      return null;
    case "none":
      return <Absence why={value.why} />;
    case "unread":
      return <NotReached label="not reached" detail={value.reason} />;
  }
}

/**
 * An absence, and its reason on demand.
 *
 * Two rules met at once here, and both were right. The craft rules forbid a
 * reason that renders only in a native `title`, because no touch or keyboard
 * user reaches it. The copy budget forbids the reason rendering by default,
 * because a sentence per cell is what turned whole screens into walls of grey —
 * eighteen rows of "no model recorded, so no harness can be derived" is not an
 * operator surface.
 *
 * So the reason is REACHABLE but not RENDERED. `details`/`summary` is the whole
 * mechanism: focusable, operable by keyboard and touch, and it needs no client
 * bundle in a server component. The closed state is one glyph — the same open
 * circle `ctowerctl` prints, which claims nothing about what is missing — and
 * the reason is one press away.
 */
export function Absence({
  why,
  label = null,
}: {
  readonly why: string;
  /** A short honest word shown beside the mark, where one exists. */
  readonly label?: string | null;
}): ReactElement {
  return (
    <details className="absence">
      <summary aria-label={label === null ? "Why this is missing" : `${label} — why`}>
        <StateGlyph name="open" />
        {label === null ? null : <span className="absence-label">{label}</span>}
      </summary>
      <span className="absence-why">{why}</span>
    </details>
  );
}

/**
 * The not-reached treatment for one fact inside a row, where the row itself is
 * real. The label is what the reader sees; the detail is the reason behind it,
 * and the label alone must already be honest — a truth that lives only in a
 * hover is a truth on a touch screen nobody has.
 */
export function NotReached({
  label,
  detail,
}: {
  readonly label: string;
  readonly detail: string;
}): ReactElement {
  // the label alone is already honest — "not reached" claims nothing — so it
  // stays visible; the reason behind it moves to the disclosure rather than a
  // native title no touch user can open
  return <Absence why={detail} label={label} />;
}

/**
 * A set this page cannot close, because a source it folds did not answer.
 *
 * The empty-set block above is a measurement: the record was consulted and
 * holds none. The trouble is that the *same* empty list arrives when nobody
 * could look, and a page that draws the two alike spends the operator's trust
 * on the one claim it cannot make. So this block names every scope that did not
 * answer, in that read's own words, and claims nothing about what they hold.
 */
export function UnknownSet({
  what,
  scopes,
}: {
  /** The thing that is not known, as a sentence subject: `What is waiting`. */
  readonly what: string;
  readonly scopes: readonly UnreachedScope[];
}): ReactElement {
  return (
    <Frame>
      <div
        className="slot"
        style={{ borderColor: "var(--warn-line)", background: "var(--warn-bg)" }}
      >
        <StateGlyph name="attn" />
        <div className="e">
          <div className="k">{what} is not known</div>
          <div
            className="d"
            title="not an empty set: the sources below did not answer, so nothing here is evidence that there are none"
          >
            {scopes.length} of the sources it is folded from did not answer
          </div>
          <div className="f" style={{ overflowWrap: "anywhere" }}>
            {scopes.map((scope) => (
              <span className="req" key={scope.key}>
                {scope.key} not reached: {scope.reason}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Frame>
  );
}
