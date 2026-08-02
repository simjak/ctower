import { recordAdapter } from "./adapter";
import { mapReading } from "./reading";
import type { Reading, RecordEvent } from "./interface";

/**
 * Which ticket the feed opens on.
 *
 * The closest thing the record holds to a session is a workflow run, so the
 * feed opens on the ticket whose workflow was driven most recently. When no
 * ticket has a workflow run, it falls back to the ticket whose record was
 * appended to most recently. Both are recorded facts and a stable rule, not a
 * hand-picked example.
 *
 * The result is a `Reading`. If every audit read failed, that is returned as
 * `unavailable` carrying the first failure — the feed must not report "no
 * recorded activity" when the truth is that it could not read any.
 */
export interface FeedFocus {
  readonly ticketId: string;
  readonly events: readonly RecordEvent[];
}

interface Stream {
  readonly ticketId: string;
  readonly audit: Reading<readonly RecordEvent[]>;
}

function latestAt(events: readonly RecordEvent[], kind: string | null): string | null {
  const matching = kind === null ? events : events.filter((event) => event.kind === kind);
  return matching.reduce<string | null>(
    (latest, event) =>
      latest === null || event.occurredAt.localeCompare(latest) > 0 ? event.occurredAt : latest,
    null
  );
}

function rank(streams: readonly Stream[]): Reading<FeedFocus> {
  const present = streams.flatMap((stream) =>
    stream.audit.state === "present" && stream.audit.value.length > 0
      ? [{ ticketId: stream.ticketId, events: stream.audit.value }]
      : []
  );
  if (present.length === 0) {
    const failures = streams.flatMap((stream) =>
      stream.audit.state === "unavailable" ? [stream.audit.failure] : []
    );
    const first = failures[0];
    if (first !== undefined) {
      return { state: "unavailable", failure: first };
    }
    return {
      state: "absent",
      source: { lands: "G5", what: "any recorded activity to render as a thread" },
    };
  }
  const ordered = [...present].sort((left, right) => {
    const leftAt = latestAt(left.events, "workflow.changed") ?? "";
    const rightAt = latestAt(right.events, "workflow.changed") ?? "";
    if (leftAt !== rightAt) {
      return rightAt.localeCompare(leftAt);
    }
    return (latestAt(right.events, null) ?? "").localeCompare(latestAt(left.events, null) ?? "");
  });
  const chosen = ordered[0];
  return chosen === undefined
    ? {
        state: "absent",
        source: { lands: "G5", what: "any recorded activity to render as a thread" },
      }
    : { state: "present", value: chosen };
}

/**
 * Resolve the feed's focus from the board, keeping every failure typed. A board
 * read that did not answer stays unavailable; it never becomes "nothing to
 * show".
 */
export async function feedFocus(): Promise<Reading<FeedFocus>> {
  const board = await recordAdapter.board();
  if (board.state !== "present") {
    return mapReading(board, (): Reading<FeedFocus> => ({
      state: "absent",
      source: { lands: "G5", what: "any recorded activity to render as a thread" },
    }));
  }
  const streams: readonly Stream[] = await Promise.all(
    board.value.entries.map(async (entry): Promise<Stream> => {
      return {
        ticketId: entry.card.ticketId,
        audit: await recordAdapter.ticketAudit(entry.card.ticketId),
      };
    })
  );
  return rank(streams);
}
