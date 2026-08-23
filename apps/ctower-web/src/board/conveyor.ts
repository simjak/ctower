import type { BoardCard, CompanyBundleDocument, MovementEvent } from "@ctower/client";
import { splitReference, workflowFacts } from "../workflows/read";
import type { ActivityClass, TransitionFact, WorkflowFact } from "../workflows/read";

/**
 * The board on the axis the work actually runs on.
 *
 * The lane view groups cards by `BoardLane`, which is the projection's summary
 * of where a ticket stands. This is the other axis and the one the workflow
 * itself uses: a card carries `stage_key`, the record moves it from stage to
 * stage, and the company definition declares which stages exist, in what order,
 * and what each move out of a stage requires.
 *
 * Three reads, all of them already served, and not one new operation:
 * `getBoard` for the cards, `exportCompanyBundle` for the workflow the company
 * declares, and `listTicketMovement` for the moves the record has recorded.
 * Nothing here derives a stage, orders one, or invents a gate.
 */
export interface StageColumn {
  readonly key: string;
  /** The workflow's own word for it; there is no second name to invent. */
  readonly label: string;
  readonly activityClass: ActivityClass | null;
  readonly cards: readonly BoardCard[];
  /**
   * The move out of this stage the definition declares, and what it requires.
   * Null at a terminal stage, and null wherever the definition declares no
   * transition — an absent gate is not an open one.
   */
  readonly leaving: TransitionFact | null;
}

export interface Conveyor {
  /** The workflow these columns are, once the record says which one it is. */
  readonly workflow: WorkflowFact | null;
  /** Why there are no columns, in one sentence, when there are none. */
  readonly silence: string | null;
  readonly stages: readonly StageColumn[];
  /** Cards the record places at no stage: they have never entered a workflow. */
  readonly unplaced: readonly BoardCard[];
  /** Cards standing at a stage this workflow does not declare. */
  readonly strays: readonly BoardCard[];
}

/**
 * Which workflow the columns are.
 *
 * The record's own answer comes first: a movement event names the
 * `workflow_ref` the ticket moved under, so if anything has ever moved on this
 * project, that is the workflow these cards run. Failing that, a company that
 * declares exactly one workflow has only one it could be. A company that
 * declares several and has moved nothing is not guessed at — the screen says
 * the record does not say, and draws no columns rather than picking one.
 */
export function conveyorOf(
  document: CompanyBundleDocument,
  cards: readonly BoardCard[],
  movement: readonly MovementEvent[]
): Conveyor {
  const declared = workflowFacts(document);
  const workflow = namedByMovement(declared, movement) ?? onlyOne(declared);
  if (workflow === null) {
    return {
      workflow: null,
      silence: silenceFor(declared, movement),
      stages: [],
      unplaced: cards.filter((card) => card.stage_key === null),
      strays: [],
    };
  }
  const known = new Set(workflow.stages.map((stage) => stage.key));
  return {
    workflow,
    silence: null,
    stages: workflow.stages.map((stage) => ({
      key: stage.key,
      label: stage.key,
      activityClass: stage.activityClass,
      cards: cards.filter((card) => card.stage_key === stage.key),
      leaving: workflow.transitions.find((move) => move.from === stage.key) ?? null,
    })),
    unplaced: cards.filter((card) => card.stage_key === null),
    strays: cards.filter((card) => card.stage_key !== null && !known.has(card.stage_key)),
  };
}

function namedByMovement(
  declared: readonly WorkflowFact[],
  movement: readonly MovementEvent[]
): WorkflowFact | null {
  const newest = [...movement].sort(
    (left, right) => right.record_position - left.record_position
  )[0];
  if (newest === undefined) {
    return null;
  }
  const [key, revision] = splitReference(newest.workflow_ref);
  return (
    declared.find(
      (fact) => fact.key === key && (revision === null || fact.revision === revision)
    ) ?? null
  );
}

function onlyOne(declared: readonly WorkflowFact[]): WorkflowFact | null {
  return declared.length === 1 ? (declared[0] ?? null) : null;
}

function silenceFor(declared: readonly WorkflowFact[], movement: readonly MovementEvent[]): string {
  if (declared.length === 0) {
    return "This company declares no workflow, so there are no stages to move through.";
  }
  if (movement.length === 0) {
    return "Nothing has moved on this project yet, and this company declares more than one workflow, so the record does not say which one these tickets run.";
  }
  return "The workflow these tickets moved under is not one this company declares.";
}

/**
 * A move the record has just recorded.
 *
 * `DESIGN.md` reserves motion for real work moving, so the conveyor animates
 * exactly one thing: a card whose stage changed between two reads. The record's
 * own `record_position` is what "since" means — a monotonic position in the
 * stream, not a clock this browser keeps — so a re-read that folds nothing new
 * animates nothing and the board stays perfectly still.
 */
export interface Moved {
  readonly ticketId: string;
  readonly from: string;
  readonly to: string;
  readonly at: string;
}

export function movedSince(
  movement: readonly MovementEvent[],
  seenPosition: number | null
): readonly Moved[] {
  if (seenPosition === null) {
    return [];
  }
  return movement
    .filter((event) => event.record_position > seenPosition)
    .sort((left, right) => left.record_position - right.record_position)
    .map((event) => ({
      ticketId: event.ticket_id,
      // The first move of a ticket's life leaves nothing: `from_stage` is the
      // empty string, and an empty string is not a stage to slide out of.
      from: event.from_stage,
      to: event.to_stage,
      at: event.occurred_at ?? "",
    }));
}

/** The newest position this read saw, which is what the next one counts from. */
export function positionOf(movement: readonly MovementEvent[]): number | null {
  return movement.reduce<number | null>(
    (highest, event) =>
      highest === null || event.record_position > highest ? event.record_position : highest,
    null
  );
}
