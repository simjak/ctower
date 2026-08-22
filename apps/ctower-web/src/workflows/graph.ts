import type { StageFact, TransitionFact, WorkflowFact } from "./read";

/**
 * The order work actually moves in, derived from the declared transitions
 * rather than from the order the stages happen to be written in.
 *
 * A workflow declares an entry stage and a set of transitions. Following them
 * from the entry stage is the only thing that makes the strip at the top of the
 * page a claim about the product instead of a rendering of an array, and it is
 * why a stage nothing routes to cannot be quietly drawn as though it were next.
 *
 * Two facts come out and they stay apart:
 *
 * - **the path** — the stages reachable by following one declared transition
 *   after another from the entry stage.
 * - **the rest** — every declared stage the path never arrives at. It is drawn,
 *   labelled for what it is, because a stage with no way in is a real thing to
 *   find on this screen and hiding it would be the console lying by omission.
 *
 * A stage that branches has more than one declared way out. The path takes the
 * first one and the stage's own card carries all of them, because a strip is a
 * strip and cannot be a graph without becoming a diagram nobody reads.
 */
export interface Ordering {
  readonly path: readonly StageFact[];
  readonly rest: readonly StageFact[];
}

export function order(workflow: WorkflowFact): Ordering {
  const byKey = new Map(workflow.stages.map((stage) => [stage.key, stage]));
  const path: StageFact[] = [];
  const walked = new Set<string>();

  let here = workflow.initialStage;
  while (here !== null && !walked.has(here)) {
    walked.add(here);
    const stage = byKey.get(here);
    if (stage !== undefined) {
      path.push(stage);
    }
    here = leaving(workflow.transitions, here).find((next) => !walked.has(next.to))?.to ?? null;
  }

  return { path, rest: workflow.stages.filter((stage) => !walked.has(stage.key)) };
}

/** Every declared way out of one stage. */
export function leaving(
  transitions: readonly TransitionFact[],
  stage: string
): readonly TransitionFact[] {
  return transitions.filter((transition) => transition.from === stage);
}

/** Every declared way in. A stage with none is an entry point or an orphan. */
export function entering(
  transitions: readonly TransitionFact[],
  stage: string
): readonly TransitionFact[] {
  return transitions.filter((transition) => transition.to === stage);
}
