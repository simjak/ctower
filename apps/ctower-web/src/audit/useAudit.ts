import { useCallback, useEffect, useState } from "react";
import type { AuditEvent, AuditPage } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * The audit read, one cursor page at a time.
 *
 * The contract pages this read and caps a page at 100 events, so a ticket with a
 * long life answers in parts. Gathering only the first page and drawing it as
 * the whole history would be the quiet kind of lie this console does not tell —
 * the operator would see a complete-looking list that stops. So the cursor the
 * API hands back is kept, the rows already gathered stay on screen, and the next
 * page is asked for only when the operator asks for it. Nothing polls:
 * `DESIGN.md` reserves motion for real work moving, and a history that repaints
 * itself on a timer is a screen moving when nothing has.
 *
 * A page turn that fails does not erase what was already answered. `page` is the
 * state of the last read asked for and `events` is everything answered so far,
 * so a refusal on page three renders under three pages of real rows instead of
 * replacing them.
 */
export interface AuditFeed {
  /** The state of the most recent read: asking, answered, refused, silent. */
  readonly page: Answer<AuditPageRead>;
  /** Every event gathered by an answered read, oldest first. */
  readonly events: readonly AuditEvent[];
  /** Where the next page starts, when the API said there is one. */
  readonly cursor: number | null;
  readonly showMore: () => void;
}

export interface AuditPageRead {
  readonly events: readonly AuditEvent[];
  readonly cursor: number | null;
}

/** The contract's own default. A page is a page, not a scroll. */
const PAGE = 50;

interface Feed {
  /** Which ticket these rows belong to; a change resets everything. */
  readonly subject: string;
  /** The cursor being read right now. */
  readonly at: number;
  readonly events: readonly AuditEvent[];
  readonly cursor: number | null;
  readonly page: Answer<AuditPageRead>;
}

function fresh(subject: string): Feed {
  return { subject, at: 0, events: [], cursor: null, page: ASKING };
}

export function useAudit(projectKey: string, ticketId: string): AuditFeed {
  const subject = `${projectKey}/${ticketId}`;
  const [feed, setFeed] = useState<Feed>(() => fresh(subject));

  useEffect(() => {
    if (feed.subject !== subject) {
      setFeed(fresh(subject));
      return;
    }
    let live = true;
    const at = feed.at;
    const load = async (): Promise<void> => {
      const answer = await ask(() =>
        reads.listTicketAuditEvents({ projectKey, ticketId, cursor: at, limit: PAGE })
      );
      if (live) {
        setFeed((current) => (current.subject === subject ? gathered(current, answer) : current));
      }
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [projectKey, ticketId, subject, feed.subject, feed.at]);

  const showMore = useCallback((): void => {
    setFeed((current) =>
      current.cursor === null ? current : { ...current, at: current.cursor, page: ASKING }
    );
  }, []);

  return { page: feed.page, events: feed.events, cursor: feed.cursor, showMore };
}

/** Fold one answered page into what is already on screen. */
function gathered(current: Feed, answer: Answer<AuditPage>): Feed {
  if (answer.kind !== "answered") {
    return { ...current, page: answer };
  }
  const page: AuditPageRead = {
    events: answer.value.events,
    cursor: answer.value.next_cursor,
  };
  return {
    ...current,
    events: [...current.events, ...page.events],
    cursor: page.cursor,
    page: { kind: "answered", value: page },
  };
}
