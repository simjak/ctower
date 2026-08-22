import type { TimelineEvent, TimelineResponse, WorkflowChangedAuditPayload } from "@ctower/client";

/**
 * What the record says about a ticket's workflow — and nothing else.
 *
 * Every field a move needs is here because a `workflow.changed` event carries
 * it: the workflow it is running, the stage it stands at, and the version that
 * move must expect. There is no read in the authored contract that returns a
 * workflow's *definition*, so the stages ahead of this ticket are not known and
 * are not drawn. The ladder is where the ticket has actually been.
 */
export interface StandingWorkflow {
  readonly reference: string;
  /** The version the next move must expect; the last one the record recorded. */
  readonly version: number;
  /** Where the ticket stands now. */
  readonly stage: string;
  /** The stages it has stood at, in the order it entered them. */
  readonly walked: readonly WalkedStage[];
  /** Whether the record has closed it. A closed workflow does not move. */
  readonly closed: boolean;
}

export interface WalkedStage {
  readonly stage: string;
  readonly enteredAt: string;
}

function isWorkflow(
  event: TimelineEvent
): event is TimelineEvent & { readonly payload: WorkflowChangedAuditPayload } {
  return event.kind === "workflow.changed";
}

/**
 * `sequence` is per stream, so the ticket's first event and the workflow's
 * first event are both 1. Ordering by it interleaves two histories into one
 * wrong story; the instant is the only ordering both streams share.
 */
export function byInstant(left: TimelineEvent, right: TimelineEvent): number {
  return left.occurred_at.localeCompare(right.occurred_at);
}

export function workflowFrom(timeline: TimelineResponse): StandingWorkflow | null {
  const moves = [...timeline.events].sort(byInstant).filter(isWorkflow);
  const last = moves.at(-1);
  if (last === undefined) {
    return null;
  }
  return {
    reference: last.payload.workflow_ref,
    version: last.payload.workflow_version,
    stage: last.payload.stage,
    walked: ladderOf(moves),
    closed: moves.some((move) => move.payload.lifecycle_facts.includes("closed")),
  };
}

/**
 * The stages the ticket entered, once each, in order.
 *
 * `resolve_close` records the stage it closed at rather than a move to it, so
 * a stage already walked is not walked a second time.
 */
function ladderOf(
  moves: readonly (TimelineEvent & { readonly payload: WorkflowChangedAuditPayload })[]
): readonly WalkedStage[] {
  const walked: WalkedStage[] = [];
  for (const move of moves) {
    if (walked.some((entry) => entry.stage === move.payload.stage)) {
      continue;
    }
    walked.push({ stage: move.payload.stage, enteredAt: move.occurred_at });
  }
  return walked;
}
