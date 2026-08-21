import type { BundleAction, BundleActionKind } from "@ctower/client";

/**
 * The plan's actions, grouped the way a person reads a change: what arrives,
 * what moves, what leaves, and what is untouched.
 *
 * The registry decides the kinds; this only sorts them. A kind it emits that
 * this file does not know would not compile, because the grouping is exhaustive
 * over the generated union — the closed world stays the contract's.
 */
export type Movement = "adds" | "changes" | "removes" | "keeps";

export interface Group {
  readonly movement: Movement;
  readonly label: string;
  /** The terraform-shaped mark: what this column does to the record. */
  readonly sign: string;
  readonly actions: readonly BundleAction[];
}

export function movementOf(kind: BundleActionKind): Movement {
  switch (kind) {
    case "create":
      return "adds";
    case "supersede":
    case "assignment_change":
    case "pointer_change":
      return "changes";
    case "deprecate":
      return "removes";
    case "reuse_exact":
    case "no_op":
      return "keeps";
  }
}

/** What the registry called the change, said once, in words. */
export function kindLabel(kind: BundleActionKind): string {
  switch (kind) {
    case "create":
      return "new";
    case "supersede":
      return "new revision";
    case "assignment_change":
      return "reassigned";
    case "pointer_change":
      return "repointed";
    case "deprecate":
      return "retired";
    case "reuse_exact":
      return "unchanged";
    case "no_op":
      return "no change";
  }
}

const ORDER: readonly {
  readonly movement: Movement;
  readonly label: string;
  readonly sign: string;
}[] = [
  { movement: "adds", label: "Added", sign: "+" },
  { movement: "changes", label: "Changed", sign: "~" },
  { movement: "removes", label: "Removed", sign: "-" },
  { movement: "keeps", label: "Unchanged", sign: "=" },
];

export function groupActions(actions: readonly BundleAction[]): readonly Group[] {
  return ORDER.map((entry) => ({
    ...entry,
    actions: actions.filter((action) => movementOf(action.kind) === entry.movement),
  }));
}

/** The one line a person reads first: how many things this plan moves. */
export function movedCount(actions: readonly BundleAction[]): number {
  return actions.filter((action) => movementOf(action.kind) !== "keeps").length;
}
