import type { ActivityClass, WorkflowFact } from "./read";

/**
 * The workflow the operator is composing.
 *
 * A draft is every field of the authored workflow schema that a person decides,
 * held as plain text and plain lists so a half-typed key is a state the editor
 * can hold rather than a value that has to be legal to exist. Turning it into
 * the document that gets sent is one function, and it happens once, at review.
 *
 * `base` is the recorded workflow this draft revises, or `null` when it is a
 * new one. That single field is the difference between a revision and an
 * arrival, and the registry is told which by the component the document
 * carries, never by a claim made on this screen.
 */
export interface StageDraft {
  readonly key: string;
  readonly activityClass: ActivityClass;
}

export interface TransitionDraft {
  readonly from: string;
  readonly to: string;
  readonly predicate: string;
}

export interface RouteDraft {
  readonly from: string;
  readonly failureClass: string;
  readonly to: string;
}

export interface WorkflowDraft {
  readonly base: WorkflowFact | null;
  readonly key: string;
  /** The workflow's own publication state; the closed set is the schema's. */
  readonly status: string;
  readonly note: string;
  readonly initialStage: string;
  readonly inputContract: string;
  readonly terminalContract: string;
  readonly executionRef: string;
  readonly gatesRef: string;
  readonly stages: readonly StageDraft[];
  readonly transitions: readonly TransitionDraft[];
  readonly routes: readonly RouteDraft[];
  /** The work-plane projects this workflow runs on, as the record binds them. */
  readonly projects: readonly string[];
  /** The same list as it stands recorded, so a change to it is countable. */
  readonly baseProjects: readonly string[];
}

/** The closed publication set the authored workflow schema declares. */
export const STATUSES: readonly string[] = [
  "draft",
  "staged",
  "published",
  "superseded",
  "revoked",
];

export const ACTIVITY_CLASSES: readonly ActivityClass[] = ["work", "verification"];

export function draftOf(workflow: WorkflowFact, projects: readonly string[]): WorkflowDraft {
  return {
    base: workflow,
    key: workflow.key,
    status: workflow.status ?? "",
    note: workflow.note ?? "",
    initialStage: workflow.initialStage ?? "",
    inputContract: workflow.inputContract ?? "",
    terminalContract: workflow.terminalContract ?? "",
    executionRef: workflow.executionRef ?? "",
    gatesRef: workflow.gatesRef ?? "",
    stages: workflow.stages.map((stage) => ({
      key: stage.key,
      activityClass: stage.activityClass ?? "work",
    })),
    transitions: workflow.transitions.map((transition) => ({
      from: transition.from,
      to: transition.to,
      predicate: transition.predicate ?? "",
    })),
    routes: workflow.routes.map((route) => ({
      from: route.from,
      failureClass: route.failureClass ?? "",
      to: route.to,
    })),
    projects,
    baseProjects: projects,
  };
}

/** A workflow that does not exist yet. Empty, because nothing about it is known. */
export function newDraft(): WorkflowDraft {
  return {
    base: null,
    key: "",
    status: "draft",
    note: "",
    initialStage: "",
    inputContract: "",
    terminalContract: "",
    executionRef: "",
    gatesRef: "",
    stages: [],
    transitions: [],
    routes: [],
    projects: [],
    baseProjects: [],
  };
}

/**
 * How many edits stand between the draft and what is recorded.
 *
 * This counts what the operator did, not what the registry would do about it —
 * those are different numbers and the page never passes one off as the other.
 * The registry's own count comes back from the plan.
 */
export function editCount(draft: WorkflowDraft): number {
  const base = draft.base;
  if (base === null) {
    // A workflow with no key is not yet a workflow. Offering to review one
    // would offer to check a document nobody has started composing.
    return draft.key.length === 0 ? 0 : 1;
  }
  const was = draftOf(base, draft.projects);
  return [
    draft.status !== was.status,
    draft.note !== was.note,
    draft.initialStage !== was.initialStage,
    draft.inputContract !== was.inputContract,
    draft.terminalContract !== was.terminalContract,
    draft.executionRef !== was.executionRef,
    draft.gatesRef !== was.gatesRef,
    !same(draft.stages.map(stageLine), was.stages.map(stageLine)),
    !same(draft.transitions.map(transitionLine), was.transitions.map(transitionLine)),
    !same(draft.routes.map(routeLine), was.routes.map(routeLine)),
    !same([...draft.projects].sort(), [...draft.baseProjects].sort()),
  ].filter(Boolean).length;
}

/** The workflow payload, exactly as the authored schema shapes it. */
export function payloadOf(
  draft: WorkflowDraft,
  revision: number
): Readonly<Record<string, unknown>> {
  const base = draft.base;
  const schema = base === null ? "ctower.workflow/v1" : base.schemaRef;
  const carried = base === null ? new Map<string, unknown>() : entryEffectsOf(base);
  return {
    failure_routes: draft.routes.map((route) => ({
      failure_class_ref: route.failureClass,
      from: route.from,
      to: route.to,
    })),
    initial_stage: draft.initialStage,
    input_contract: draft.inputContract,
    key: draft.key,
    note: draft.note,
    policy_refs: { execution: draft.executionRef, gates: draft.gatesRef },
    revision,
    schema,
    stages: draft.stages.map((stage) => stageOf(stage, schema, carried)),
    status: draft.status,
    terminal_contract: draft.terminalContract,
    transitions: draft.transitions.map((transition) => ({
      from: transition.from,
      predicate_ref: transition.predicate,
      to: transition.to,
    })),
  };
}

function stageOf(
  stage: StageDraft,
  schema: string,
  carried: ReadonlyMap<string, unknown>
): Readonly<Record<string, unknown>> {
  const declared = { activity_class: stage.activityClass, key: stage.key };
  return schema === "ctower.workflow/v2"
    ? { ...declared, entry_effects: carried.get(stage.key) ?? [] }
    : declared;
}

/**
 * A v2 stage declares entry effects, and this console does not author one. They
 * are carried through by stage key so revising a v2 workflow never silently
 * drops the dispatch a stage was declared to make.
 */
function entryEffectsOf(base: WorkflowFact): Map<string, unknown> {
  const stages = base.payload.stages;
  if (!Array.isArray(stages)) {
    return new Map();
  }
  const carried = new Map<string, unknown>();
  for (const stage of stages as readonly unknown[]) {
    if (typeof stage === "object" && stage !== null && !Array.isArray(stage)) {
      const held = stage as Readonly<Record<string, unknown>>;
      const key = held.key;
      if (typeof key === "string" && held.entry_effects !== undefined) {
        carried.set(key, held.entry_effects);
      }
    }
  }
  return carried;
}

function stageLine(stage: StageDraft): string {
  return `${stage.key}/${stage.activityClass}`;
}

function transitionLine(transition: TransitionDraft): string {
  return `${transition.from}>${transition.to}/${transition.predicate}`;
}

function routeLine(route: RouteDraft): string {
  return `${route.from}!${route.failureClass}>${route.to}`;
}

function same(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}
