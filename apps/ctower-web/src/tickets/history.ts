import type { TimelineEvent } from "@ctower/client";
import { byInstant } from "./workflow";

/**
 * The ticket's history, said as what a person did.
 *
 * `workflow.changed` covers three different acts and names which in its own
 * `operation`, so a start reads as work starting rather than as a move from a
 * stage that never existed. Nothing here restates a payload the operator can
 * already see elsewhere on the page.
 */
export interface Entry {
  readonly id: string;
  readonly at: string;
  /** What happened, in the operator's words. */
  readonly what: string;
  /** The one fact that makes it specific, when the payload carries one. */
  readonly detail: string | null;
  /** Whether that fact is machine-owned text. */
  readonly machine: boolean;
  readonly actor: string;
}

/**
 * What this history contains, said on the page.
 *
 * The timeline read carries four event kinds. Blockers and admissions are work
 * intents on a third stream and are not in it, and a section headed "History"
 * that quietly omitted them would read as "nothing else happened".
 */
export const HISTORY_SCOPE =
  "Raising, custody, comments and stage moves. Work intents such as admitting " +
  "or blocking are on another read.";

export function historyOf(events: readonly TimelineEvent[]): readonly Entry[] {
  return [...events].sort(byInstant).map(entryOf);
}

function entryOf(event: TimelineEvent): Entry {
  const said = saidBy(event);
  return {
    id: event.event_id,
    at: event.occurred_at,
    what: said.what,
    detail: said.detail,
    machine: said.machine,
    actor: event.actor_principal_id,
  };
}

interface Said {
  readonly what: string;
  readonly detail: string | null;
  readonly machine: boolean;
}

function saidBy(event: TimelineEvent): Said {
  switch (event.kind) {
    case "ticket.created":
      return { what: "Raised", detail: null, machine: false };
    case "ticket.custody_transferred":
      return { what: "Custody moved", detail: null, machine: false };
    case "ticket.comment_added":
      return {
        what: "Commented",
        detail: "body" in event.payload ? event.payload.body : null,
        machine: false,
      };
    case "workflow.changed":
      return "operation" in event.payload
        ? moved(event.payload.operation, event.payload.stage, event.payload.source_stage)
        : { what: "Workflow changed", detail: null, machine: false };
  }
}

function moved(
  operation: "start" | "transition" | "resolve_close",
  stage: string,
  from: string
): Said {
  switch (operation) {
    case "start":
      return { what: "Work started", detail: stage, machine: true };
    case "transition":
      return { what: "Stage moved", detail: `${from} → ${stage}`, machine: true };
    case "resolve_close":
      return { what: "Resolved and closed", detail: stage, machine: true };
  }
}
