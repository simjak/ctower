import type { TimelineEvent, WorkflowChangedAuditPayload } from "@ctower/client";

/**
 * The recorded history of one ticket, in the operator's words.
 *
 * A timeline entry's `kind` is the record's own event name. It never renders:
 * the board critique caught an API operation drawn as a step label, and
 * `ticket.custody_transferred` is the same fault one level down. Each kind maps
 * to what a person did, and the one line under it is read out of that event's
 * own payload — never summarised, never inferred from a neighbouring event.
 *
 * `workflow.changed` covers three different acts and says which in its own
 * `operation`, so it is read there. Drawing a start and a close as "Stage
 * moved" would put one word on three facts, and the start would render with an
 * empty stage on the left of an arrow that never happened.
 */
export interface Moment {
  readonly id: string;
  /** What happened, as a person would say it. */
  readonly what: string;
  /** One line of the event's own recorded detail, when it carries one. */
  readonly detail: string | null;
  readonly at: string;
}

/**
 * Newest first, by when it happened.
 *
 * Not by `sequence`: that number is per-stream, so the ticket's own first event
 * and the workflow's own first event are both `1`, and ordering by it
 * interleaves two histories into one wrong story.
 */
export function momentsOf(events: readonly TimelineEvent[]): readonly Moment[] {
  return [...events]
    .sort((left, right) => right.occurred_at.localeCompare(left.occurred_at))
    .map((event) => ({
      id: event.event_id,
      what: whatOf(event),
      detail: detailOf(event),
      at: event.occurred_at,
    }));
}

const WHAT: Readonly<Record<Exclude<TimelineEvent["kind"], "workflow.changed">, string>> = {
  "ticket.created": "Raised",
  "ticket.custody_transferred": "Custody moved",
  "ticket.comment_added": "Comment added",
};

const DID: Readonly<Record<WorkflowChangedAuditPayload["operation"], string>> = {
  start: "Work started",
  transition: "Stage moved",
  resolve_close: "Closed",
};

function whatOf(event: TimelineEvent): string {
  if (event.kind !== "workflow.changed") {
    return WHAT[event.kind];
  }
  return "operation" in event.payload ? DID[event.payload.operation] : "Stage moved";
}

/**
 * The four payloads are a closed union and each one is read for exactly the
 * fact it holds. The discriminator is the event's `kind`, so a payload is never
 * probed for a field it may not have.
 */
function detailOf(event: TimelineEvent): string | null {
  switch (event.kind) {
    case "ticket.created":
      return "source_ref" in event.payload ? event.payload.source_ref : null;
    case "ticket.custody_transferred":
      return "reason" in event.payload ? event.payload.reason : null;
    case "ticket.comment_added":
      return "body" in event.payload ? event.payload.body : null;
    case "workflow.changed":
      return "operation" in event.payload ? stageOf(event.payload) : null;
  }
}

/** Where the work went, and only the halves the record actually filled in. */
function stageOf(payload: WorkflowChangedAuditPayload): string | null {
  if (payload.operation === "transition") {
    return `${payload.source_stage} → ${payload.stage}`;
  }
  if (payload.operation === "start") {
    return payload.stage;
  }
  return payload.lifecycle_facts.length === 0 ? null : payload.lifecycle_facts.join(", ");
}

/**
 * A recorded instant, as the record holds it: UTC, to the minute.
 *
 * Not the reader's locale. Two people looking at the same board must be looking
 * at the same instant, and the record's own zone is the only one both of them
 * can check against the log.
 */
export function instant(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? iso : `${at.toISOString().slice(0, 16).replace("T", " ")}Z`;
}
