import { recordAdapter } from "./adapter";
import { mapReading } from "./reading";
import { rankCandidates } from "./selectors";
import type { Candidate, Ranked } from "./selectors";
import type { Reading, RecordEvent } from "./interface";

/**
 * Which ticket the feed opens on.
 *
 * The closest thing the record holds to a session is a workflow run, so the
 * feed opens on the ticket whose workflow was driven most recently, falling
 * back to the ticket appended to most recently.
 *
 * The ranking runs over a fan-out of audit reads, and a fan-out can be *partly*
 * unavailable. `rankCandidates` keeps that visible: an audit that did not
 * answer is counted, never dropped, and the feed states on its face that the
 * ranking is provisional. A stream this read could not see might have been the
 * newer one, and the screen may not quietly imply otherwise.
 */
export interface FeedFocus {
  readonly ticketId: string;
  readonly events: readonly RecordEvent[];
}

export type FocusReading = Reading<Ranked<FeedFocus>>;

const NO_ACTIVITY = {
  lands: "G5",
  what: "any recorded activity to render as a thread",
} as const;

function latestAt(events: readonly RecordEvent[], kind: string | null): string {
  const matching = kind === null ? events : events.filter((event) => event.kind === kind);
  return matching.reduce<string>(
    (latest, event) => (event.occurredAt.localeCompare(latest) > 0 ? event.occurredAt : latest),
    ""
  );
}

/** Order by the last workflow move, then by the last appended event. */
export function orderKey(events: readonly RecordEvent[]): string {
  return `${latestAt(events, "workflow.changed")}|${latestAt(events, null)}`;
}

function candidateOf(
  ticketId: string,
  audit: Reading<readonly RecordEvent[]>
): Candidate<FeedFocus> {
  return {
    reading: mapReading(audit, (events): Reading<FeedFocus> =>
      events.length === 0
        ? { state: "absent", source: NO_ACTIVITY }
        : { state: "present", value: { ticketId, events } }
    ),
    orderBy: audit.state === "present" ? orderKey(audit.value) : "",
  };
}

export async function feedFocus(): Promise<FocusReading> {
  const board = await recordAdapter.board();
  if (board.state !== "present") {
    return mapReading(board, (): FocusReading => ({ state: "absent", source: NO_ACTIVITY }));
  }
  const candidates: readonly Candidate<FeedFocus>[] = await Promise.all(
    board.value.entries.map(async (entry): Promise<Candidate<FeedFocus>> =>
      candidateOf(entry.card.ticketId, await recordAdapter.ticketAudit(entry.card.ticketId))
    )
  );
  return rankCandidates(candidates, NO_ACTIVITY);
}
