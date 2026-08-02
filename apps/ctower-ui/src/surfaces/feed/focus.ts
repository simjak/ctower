import { recordAdapter } from "@/read/adapter";
import type { BoardSnapshot, RecordEvent } from "@/read/interface";

/**
 * Which ticket the feed opens on.
 *
 * The closest thing the record holds to a session is a workflow run, so the
 * feed opens on the ticket whose workflow was driven most recently. When no
 * ticket has a workflow run, it falls back to the ticket whose record was
 * appended to most recently. Both are recorded facts and a stable rule, not a
 * hand-picked example.
 */
export interface FeedFocus {
  readonly ticketId: string;
  readonly events: readonly RecordEvent[];
}

function latestAt(events: readonly RecordEvent[], kind: string | null): string | null {
  const matching = kind === null ? events : events.filter((event) => event.kind === kind);
  return matching.reduce<string | null>(
    (latest, event) =>
      latest === null || event.occurredAt.localeCompare(latest) > 0 ? event.occurredAt : latest,
    null
  );
}

export async function focusTicket(snapshot: BoardSnapshot): Promise<FeedFocus | null> {
  const streams = await Promise.all(
    snapshot.entries.map(async (entry) => {
      const audit = await recordAdapter.ticketAudit(entry.card.ticketId);
      return {
        ticketId: entry.card.ticketId,
        events: audit.state === "present" ? audit.value : [],
      };
    })
  );
  const ranked = streams
    .map((stream) => ({
      ...stream,
      workflowAt: latestAt(stream.events, "workflow.changed"),
      appendedAt: latestAt(stream.events, null),
    }))
    .filter((stream) => stream.events.length > 0);
  if (ranked.length === 0) {
    return null;
  }
  const withWorkflow = ranked.filter((stream) => stream.workflowAt !== null);
  const pool = withWorkflow.length > 0 ? withWorkflow : ranked;
  const chosen = [...pool].sort((left, right) =>
    (right.workflowAt ?? right.appendedAt ?? "").localeCompare(
      left.workflowAt ?? left.appendedAt ?? ""
    )
  )[0];
  return chosen === undefined ? null : { ticketId: chosen.ticketId, events: chosen.events };
}
