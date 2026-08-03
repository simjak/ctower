import type { RecordEvent } from "@/read/interface";

/**
 * Derivations over one ticket's recorded event stream.
 *
 * Every value returned here is a field the record wrote, or an ordering of
 * those fields. Nothing is inferred from a title, an identifier's spelling, or
 * the absence of an event.
 */

export interface StageEntry {
  readonly stage: string;
  readonly enteredAt: string;
  readonly leftAt: string | null;
  readonly workflowRef: string;
  readonly lifecycleFacts: readonly string[];
}

function payloadString(event: RecordEvent, key: string): string | null {
  const value: unknown = event.payload[key];
  return typeof value === "string" ? value : null;
}

function payloadStrings(event: RecordEvent, key: string): readonly string[] {
  const value: unknown = event.payload[key];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function byTime(events: readonly RecordEvent[]): readonly RecordEvent[] {
  return [...events].sort((left, right) => left.occurredAt.localeCompare(right.occurredAt));
}

export function ofKind(events: readonly RecordEvent[], kind: string): readonly RecordEvent[] {
  return events.filter((event) => event.kind === kind);
}

export function operationOf(event: RecordEvent): string | null {
  return payloadString(event, "operation");
}

/** The stages this ticket's workflow actually entered, in recorded order. */
export function stagesFrom(events: readonly RecordEvent[]): readonly StageEntry[] {
  const workflow = byTime(ofKind(events, "workflow.changed"));
  const entries: StageEntry[] = [];
  for (const event of workflow) {
    const stage = payloadString(event, "stage");
    const workflowRef = payloadString(event, "workflow_ref");
    if (stage === null || workflowRef === null) {
      continue;
    }
    const facts = payloadStrings(event, "lifecycle_facts");
    const fresh: StageEntry = {
      stage,
      enteredAt: event.occurredAt,
      leftAt: null,
      workflowRef,
      lifecycleFacts: facts,
    };
    const lastIndex = entries.length - 1;
    const last = entries[lastIndex];
    if (last === undefined) {
      entries.push(fresh);
      continue;
    }
    if (last.stage === stage) {
      entries[lastIndex] = { ...last, lifecycleFacts: [...last.lifecycleFacts, ...facts] };
      continue;
    }
    entries[lastIndex] = { ...last, leftAt: event.occurredAt };
    entries.push(fresh);
  }
  return entries;
}

export function workflowRefOf(events: readonly RecordEvent[]): string | null {
  const stages = stagesFrom(events);
  return stages.at(0)?.workflowRef ?? null;
}

/** A one-line rendering of what the record wrote, built only from its fields. */
export function eventHeadline(event: RecordEvent): string {
  const operation = operationOf(event);
  const stage = payloadString(event, "stage");
  const parts = [event.kind];
  if (operation !== null) {
    parts.push(operation);
  }
  if (stage !== null) {
    parts.push(`stage ${stage}`);
  }
  return parts.join(" · ");
}

export function payloadText(event: RecordEvent): string {
  return JSON.stringify(event.payload, null, 2);
}

export function digestOf(event: RecordEvent): string | null {
  return payloadString(event, "candidate_digest");
}

export function isProof(event: RecordEvent): boolean {
  return event.kind === "proof.changed";
}

/**
 * A comment is `ticket.comment_added`, the kind the record actually appends.
 *
 * Round-3 QA (#241) traced the Comments panel's "lands with #186" to this
 * filter: it matched `comment.*`, which is in no event enum, so the panel could
 * only ever render "ctower does not record ticket comments" — a false claim
 * about the record, standing behind a citation for an unrelated issue. The
 * record has carried `EventKind.TICKET_COMMENT_ADDED` all along.
 */
export function isComment(event: RecordEvent): boolean {
  return event.kind === "ticket.comment_added";
}

/**
 * A relation is a `work.changed` whose recorded operation is `relation_added`.
 *
 * Same defect as `isComment`: this matched `relation.*`, a kind that does not
 * exist, so "Depends on" could never fill in. Relations are an *operation* on
 * the work-changed kind, per the authored event envelope.
 */
export function isRelation(event: RecordEvent): boolean {
  return event.kind === "work.changed" && operationOf(event) === "relation_added";
}
