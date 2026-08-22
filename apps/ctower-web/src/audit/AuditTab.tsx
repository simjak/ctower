import { useState } from "react";
import type { ReactElement } from "react";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { Mark } from "../ui/marks";
import { Button, Chip, Mono } from "../ui/primitives";
import { rowOf } from "./events";
import type { AuditRow, Fact } from "./events";
import { useAudit } from "./useAudit";

/**
 * The work behind a ticket, as the record kept it.
 *
 * This is the read the timeline does not have. A timeline answers four kinds of
 * event; the audit answers nine, and the five it adds are the ones an operator
 * actually asks about — what was admitted, what was blocked, whose priority
 * changed, which proof moved, which crew sat down and what it cost.
 *
 * The list runs oldest first, the way the record wrote it, because an audit read
 * backwards stops being an account of how the ticket got here.
 */
export function AuditTab({
  projectKey,
  ticketId,
}: {
  readonly projectKey: string;
  readonly ticketId: string;
}): ReactElement {
  const feed = useAudit(projectKey, ticketId);
  const rows = feed.events.map(rowOf);

  if (rows.length === 0) {
    return <FirstAnswer feed={feed} />;
  }

  return (
    <div>
      <ol className="m-0 list-none p-0">
        {rows.map((row, index) => (
          <Entry key={row.id} row={row} sameDay={rows[index - 1]?.day === row.day} />
        ))}
      </ol>
      {feed.page.kind === "answered" ? null : (
        <div className="mt-3">
          <FirstAnswer feed={feed} />
        </div>
      )}
      {feed.cursor === null || feed.page.kind !== "answered" ? null : (
        <Button size="sm" className="mt-3" onClick={feed.showMore}>
          Older
        </Button>
      )}
    </div>
  );
}

/** Before there is a list, the state of the read is the whole screen. */
function FirstAnswer({
  feed,
}: {
  readonly feed: ReturnType<typeof useAudit>;
}): ReactElement | null {
  switch (feed.page.kind) {
    case "asking":
      return <Asking what="Reading this ticket's record" />;
    case "refused":
      return (
        <Refused
          problem={feed.page.problem}
          action="Nothing was read. Reopen the card to ask again."
        />
      );
    case "unreachable":
      return (
        <Unreachable
          detail={feed.page.detail}
          action="This is not a ticket without history; it is a history that was not read."
        />
      );
    case "malformed":
      return <Malformed detail={feed.page.detail} />;
    case "answered":
      return (
        <p className="m-0 py-6 text-sm text-muted">
          Nothing has been recorded against this ticket yet.
        </p>
      );
  }
}

/**
 * One recorded act: when, what somebody did, and the words they gave for it.
 *
 * The event's own name, its hash and its position in the record are real and are
 * reachable — they are what an operator quotes when something is disputed — but
 * they are not what the row is about, so they sit behind the disclosure D9 asks
 * for rather than in front of the sentence.
 */
function Entry({
  row,
  sameDay,
}: {
  readonly row: AuditRow;
  readonly sameDay: boolean;
}): ReactElement {
  const [open, setOpen] = useState(false);

  return (
    <li className="border-t border-line first:border-t-0">
      {sameDay ? null : <Mono className="block bg-raised px-3 py-1 text-muted">{row.day}</Mono>}
      <div className="flex items-baseline gap-2 px-3 py-2">
        <Mono className="shrink-0 text-muted">{row.time}</Mono>
        {row.mark === null ? <span className="w-[1.4em] shrink-0" /> : <Mark name={row.mark} />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{row.headline}</span>
            {row.chip === null ? null : <Chip>{row.chip}</Chip>}
          </div>
          {row.detail === null ? null : (
            <p className="m-0 mt-0.5 text-sm text-muted">{row.detail}</p>
          )}
        </div>
        <button
          type="button"
          aria-expanded={open}
          aria-label={open ? "Hide the recorded fact" : "Show the recorded fact"}
          className="shrink-0 cursor-pointer rounded-sm border border-transparent px-1 text-2xs text-muted hover:bg-raised"
          onClick={(): void => {
            setOpen(!open);
          }}
        >
          (i)
        </button>
      </div>
      {/* The record's own identifiers take the row's full width rather than the
          sentence's column: a digest broken over four lines to fit beside a
          headline is a digest nobody can read back to anyone. */}
      {open ? <Facts facts={row.facts} /> : null}
    </li>
  );
}

function Facts({ facts }: { readonly facts: readonly Fact[] }): ReactElement {
  return (
    <dl className="mt-0 mb-0 grid grid-cols-[5rem_minmax(0,1fr)] gap-x-3 gap-y-0.5 border-l-2 border-line px-3 pb-2.5">
      {facts.map((fact) => (
        <div key={fact.label + fact.value} className="contents">
          <dt className="text-2xs text-muted">{fact.label}</dt>
          <dd className="m-0 min-w-0 break-words">
            {fact.machine ? (
              <Mono className="text-muted">{fact.value}</Mono>
            ) : (
              <span className="text-xs text-muted">{fact.value}</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
