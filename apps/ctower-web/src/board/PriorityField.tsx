import type { ReactElement } from "react";
import type { BoardCard, Priority } from "@ctower/client";
import { cn } from "../ui/cn";

/**
 * How urgent, asked of the board already on screen.
 *
 * This is not the project field's kind of control and is deliberately not drawn
 * as one. `project_key` is a required parameter of the board read, so choosing
 * a project asks ctower a new question at a new watermark; priority narrows the
 * one answer already in hand and touches the network not at all. `getBoard`
 * does carry a `priority` parameter and this could have been a second read —
 * it is not, because two reads put two watermarks in one glance and the
 * operator comparing a `P0` count against a `P1` count would be comparing two
 * different folds of the record.
 *
 * Each choice carries what it would keep. While the board has not answered
 * there is nothing to count, and nothing is drawn — a zero shown before a read
 * lands is a claim about cards nobody has counted yet.
 */
export type PriorityChoice = Priority | "any";

export const PRIORITIES: readonly PriorityChoice[] = ["any", "P0", "P1", "P2"];

export function atPriority(
  cards: readonly BoardCard[],
  choice: PriorityChoice
): readonly BoardCard[] {
  return choice === "any" ? cards : cards.filter((card) => card.priority === choice);
}

export function countsOf(
  cards: readonly BoardCard[] | null
): Readonly<Record<PriorityChoice, number>> | null {
  if (cards === null) {
    return null;
  }
  return {
    any: cards.length,
    P0: atPriority(cards, "P0").length,
    P1: atPriority(cards, "P1").length,
    P2: atPriority(cards, "P2").length,
  };
}

export function PriorityField({
  priority,
  counts,
  onChoose,
}: {
  readonly priority: PriorityChoice;
  /** `null` until the board has answered. */
  readonly counts: Readonly<Record<PriorityChoice, number>> | null;
  readonly onChoose: (choice: PriorityChoice) => void;
}): ReactElement {
  return (
    <div className="flex items-center gap-2">
      <span className="text-2xs text-muted">Priority</span>
      <div className="flex overflow-hidden rounded-sm border border-line">
        {PRIORITIES.map((choice) => (
          <button
            key={choice}
            type="button"
            aria-pressed={choice === priority}
            className={cn(
              "h-7 cursor-pointer border-l border-line px-2.5 text-xs first:border-l-0",
              choice === priority
                ? "bg-amber font-semibold text-on-amber"
                : "bg-transparent text-muted hover:bg-raised"
            )}
            onClick={(): void => {
              onChoose(choice);
            }}
          >
            {choice === "any" ? "Any" : choice}
            {counts === null ? null : (
              <span className="ml-1.5 opacity-70">{String(counts[choice])}</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
