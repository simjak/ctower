import type { ReactElement, ReactNode } from "react";
import type { TicketSession } from "@ctower/client";
import type { Answer } from "../api/client";
import { Card, CardBody, CardHeader, CardTitle } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { Hint } from "../ui/form";
import { activityOf, deliveryOf, statusesOf, usageOf } from "./activity";
import { Waiting } from "./Waiting";

/**
 * An agent's home, opened on what its team has actually done.
 *
 * Four things sit on this tab and only two of them are the record's. Runs, how
 * they ended and what they spent are counted from recorded work. Cached tokens
 * and money are not counted, because nothing records them — they are drawn as
 * absent, holding their own place in the row under a label of the same weight,
 * so a reader meets a gap where a gap is rather than two figures and a silence.
 *
 * The scope caveat renders as a sentence instead of hiding in a tooltip. What
 * a number counts is a fact about that number; only the reason it cannot yet be
 * narrower is rationale, and that is what sits behind the disclosure.
 */
const SCOPE_REASON =
  "A recorded run keeps the seat that ran it, and an agent is named somewhere else; nothing yet ties one to the other.";
const CACHED_REASON = "Recorded work counts what went in and what came out, and nothing else.";
const SPEND_REASON = "No price is recorded against any model, so a total would be a guess.";

export function Dashboard({
  work,
}: {
  readonly work: Answer<readonly TicketSession[]>;
}): ReactElement {
  if (work.kind !== "answered") {
    return <Waiting answer={work} />;
  }
  return (
    <div className="flex flex-col gap-4">
      {/* The disclosure travels inside the sentence rather than beside it, so a
          narrow tab wraps it with the words instead of stranding it alone at
          the far edge of the line above. */}
      <p className="m-0 text-xs text-muted">
        Every figure here counts the whole team&rsquo;s recorded work.{" "}
        <span className="inline-block translate-y-0.5">
          <Hint text={SCOPE_REASON} />
        </span>
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <RunActivity runs={work.value} />
        <ByStatus runs={work.value} />
        <SuccessRate runs={work.value} />
      </div>
      <Cost runs={work.value} />
    </div>
  );
}

function RunActivity({ runs }: { readonly runs: readonly TicketSession[] }): ReactElement {
  const activity = activityOf(runs);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Run activity</CardTitle>
      </CardHeader>
      <CardBody className="grid gap-3">
        <Figure label="Runs recorded" value={activity.runs} />
        <Figure label="Open now" value={activity.open} />
        <Figure label="Last started" value={activity.lastStarted} size="small" />
      </CardBody>
    </Card>
  );
}

/**
 * The distribution, drawn in the marks the CLI prints for the same states.
 *
 * A bucket only appears when a run is in it. Drawing every word the vocabulary
 * has, most of them at nought, would fill the card with states this team has
 * never been in.
 */
function ByStatus({ runs }: { readonly runs: readonly TicketSession[] }): ReactElement {
  const statuses = statusesOf(runs);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Runs by status</CardTitle>
      </CardHeader>
      <CardBody>
        {statuses.length === 0 ? (
          <p className="m-0 text-sm text-muted">No run has been recorded yet.</p>
        ) : (
          <ul className="m-0 list-none space-y-2 p-0">
            {statuses.map((status) => (
              <li key={status.word} className="flex items-baseline gap-1.5">
                {/* A status with no glyph still holds the glyph's column, so
                    every word in the card starts on the same line. Drawing
                    nothing is the rule; drawing nothing *and* moving is a
                    second, accidental signal. */}
                {status.mark === null ? (
                  <span aria-hidden className="mono inline-block w-[1.4em] shrink-0" />
                ) : (
                  <Mark name={status.mark} />
                )}
                <span className="min-w-0 flex-1 truncate text-sm">{status.word}</span>
                <span className="shrink-0 text-sm font-semibold">{status.runs}</span>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

function SuccessRate({ runs }: { readonly runs: readonly TicketSession[] }): ReactElement {
  const delivery = deliveryOf(runs);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Success rate</CardTitle>
      </CardHeader>
      <CardBody>
        {delivery.finished === 0 ? (
          // No share at all rather than a nought: nought would say every
          // finished run failed, and none has finished.
          <p className="m-0 text-sm text-muted">No run has finished yet.</p>
        ) : (
          <>
            <p className="m-0 text-2xl leading-none font-bold tracking-[-0.02em]">
              {Math.round((delivery.delivered / delivery.finished) * 100)}%
            </p>
            <p className="mt-2 mb-0 text-xs text-muted">
              {delivery.delivered} of {delivery.finished} finished runs delivered.
            </p>
          </>
        )}
        {delivery.unrecorded === 0 ? null : (
          <p className="mt-1 mb-0 text-2xs text-muted">
            Finished with no result recorded: {delivery.unrecorded} — counted on neither side.
          </p>
        )}
      </CardBody>
    </Card>
  );
}

/**
 * What the work spent. Two of these four are the record's and two are gaps,
 * and the gaps keep their place in the row on purpose — a missing figure that
 * is simply left out reads as a figure of nought.
 *
 * When no run recorded usage at all the two real figures go absent too, rather
 * than drawing the nought their own sum produces. A sum over nothing is not a
 * measurement of nothing: one says the record was not asked, the other says the
 * team spent nothing, and only the first of those is true here.
 */
function Cost({ runs }: { readonly runs: readonly TicketSession[] }): ReactElement {
  const usage = usageOf(runs);
  const measured = usage.counted > 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Cost</CardTitle>
      </CardHeader>
      <CardBody className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Figure label="Input tokens" value={measured ? count(usage.input) : null} />
        <Figure label="Output tokens" value={measured ? count(usage.output) : null} />
        <NotRecorded label="Cached tokens" reason={CACHED_REASON} />
        <NotRecorded label="Total spend" reason={SPEND_REASON} />
      </CardBody>
      {measured ? (
        <p className="m-0 border-t border-line px-4 py-2.5 text-2xs text-muted">
          {usage.counted === runs.length
            ? `Counted across all ${String(runs.length)} runs.`
            : `Counted across ${String(usage.counted)} of ${String(runs.length)} runs; the rest recorded no usage.`}
        </p>
      ) : null}
    </Card>
  );
}

/** Grouped, because six figures unbroken is a string an operator has to count. */
function count(total: number): string {
  return total.toLocaleString("en-GB");
}

function Figure({
  label,
  value,
  size = "large",
}: {
  readonly label: string;
  readonly value: ReactNode;
  readonly size?: "large" | "small";
}): ReactElement {
  return (
    <div className="min-w-0">
      <p className="m-0 text-2xs text-muted">{label}</p>
      {value === null ? (
        <p className="mt-1 mb-0 text-sm text-muted">none recorded</p>
      ) : (
        <p
          className={
            size === "large"
              ? "mt-1 mb-0 text-2xl leading-none font-bold tracking-[-0.02em]"
              : "mt-1 mb-0 text-sm"
          }
        >
          {value}
        </p>
      )}
    </div>
  );
}

/**
 * A figure nothing records, holding its own place in the row.
 *
 * It draws no mark. A state with no recorded fact draws nothing at all, and an
 * absence is not a state — borrowing the warning glyph here would report a gap
 * in the record as a condition of the work.
 */
function NotRecorded({
  label,
  reason,
}: {
  readonly label: string;
  readonly reason: string;
}): ReactElement {
  return (
    <div className="min-w-0">
      <p className="m-0 flex items-center gap-1.5 text-2xs text-muted">
        {label}
        <Hint text={reason} />
      </p>
      <p className="mt-1 mb-0 text-sm text-muted">not recorded yet</p>
    </div>
  );
}
