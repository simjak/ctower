import { useState } from "react";
import type { ReactElement } from "react";
import { instant } from "../board/history";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { Mark } from "../ui/marks";
import { Button, Chip, Mono } from "../ui/primitives";
import { rowOf } from "./events";
import type { AuditRow, Fact } from "./events";
import { useAudit } from "./useAudit";

/**
 * Everything the record kept against one ticket.
 *
 * This is the read the timeline does not have. `getTicketTimeline` answers four
 * kinds of event; `listTicketAuditEvents` answers nine, and the five it adds
 * are the ones an operator asks about — what was admitted, what was blocked,
 * whose priority changed, which proof step happened, and which crew sat down
 * and what the session cost.
 *
 * Oldest first, the way the record wrote it. A history read backwards stops
 * being an account of how the ticket got here, and the contract's cursor runs
 * forwards: page one is the oldest page, so a list drawn newest-first would
 * have to fill in from the middle.
 */
/**
 * The words both surfaces use for this feed, held once so they cannot drift.
 *
 * The Board panel and the ticket's own page answer the same question from the
 * same read. They said it in two different headings until the commander ruled
 * this read canonical (T-009), and two headings over one answer is how a reader
 * learns to expect two different things. The heading now lives with the feed.
 */
export const WORK_TITLE = "Work";
export const WORK_SCOPE = "Every act the record kept against this ticket.";

export function AuditFeed({
  projectKey,
  ticketId,
}: {
  readonly projectKey: string;
  readonly ticketId: string;
}): ReactElement {
  const feed = useAudit(projectKey, ticketId);
  const rows = feed.events.map(rowOf);

  if (rows.length === 0) {
    return <Standing feed={feed} />;
  }

  return (
    <div>
      <ol className="m-0 list-none space-y-2.5 p-0">
        {rows.map((row) => (
          <Entry key={row.id} row={row} />
        ))}
      </ol>
      {feed.page.kind === "answered" ? null : (
        <div className="mt-2.5">
          <Standing feed={feed} />
        </div>
      )}
      {/* The cursor runs forwards, so the page behind this one is the *newer*
          one. Labelling it "older" would have been a lie about which direction
          the record is being read in. */}
      {feed.cursor === null || feed.page.kind !== "answered" ? null : (
        <Button size="sm" className="mt-3" onClick={feed.showMore}>
          Newer
        </Button>
      )}
    </div>
  );
}

/** Before there is a list, the state of the read is the whole section. */
function Standing({ feed }: { readonly feed: ReturnType<typeof useAudit> }): ReactElement {
  switch (feed.page.kind) {
    case "asking":
      return <Asking what="Reading what it did" />;
    case "refused":
      return <Refused problem={feed.page.problem} action="No history was read." />;
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
      return <p className="m-0 text-sm text-muted">Nothing is recorded against this ticket yet.</p>;
  }
}

/**
 * One recorded act: what somebody did, when, and the words they gave for it.
 *
 * The event's own name, its hash and its position in the record are real and
 * are what an operator quotes when something is disputed — but they are not
 * what the row is about, so they sit behind the disclosure D9 asks for rather
 * than in front of the sentence.
 */
function Entry({ row }: { readonly row: AuditRow }): ReactElement {
  const [open, setOpen] = useState(false);

  return (
    <li className="border-l border-line pl-3">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {row.mark === null ? null : <Mark name={row.mark} />}
        <span className="text-sm font-medium">{row.headline}</span>
        {row.chip === null ? null : <Chip>{row.chip}</Chip>}
        <Mono className="text-muted" title={row.at}>
          {instant(row.at)}
        </Mono>
        <button
          type="button"
          aria-expanded={open}
          aria-label={open ? "Hide the recorded fact" : "Show the recorded fact"}
          className="cursor-pointer rounded-sm px-1 text-2xs text-muted hover:bg-raised"
          onClick={(): void => {
            setOpen(!open);
          }}
        >
          (i)
        </button>
      </div>
      {row.detail === null ? null : (
        <p className="m-0 text-xs break-words text-muted">{row.detail}</p>
      )}
      {open ? <Facts facts={row.facts} /> : null}
    </li>
  );
}

function Facts({ facts }: { readonly facts: readonly Fact[] }): ReactElement {
  return (
    <dl className="mt-1.5 mb-0 grid grid-cols-[5rem_minmax(0,1fr)] gap-x-3 gap-y-0.5">
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
