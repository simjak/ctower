import type { ReactElement, ReactNode } from "react";
import type { BoardCard, BoardLane, Priority } from "@ctower/client";
import { Chip, Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";
import type { MarkName } from "../ui/marks";

/**
 * The small facts this page draws in more than one place, each drawn one way.
 *
 * The lane words are the contract's own closed set said in the operator's
 * language; nothing here invents a state the record did not answer with.
 */
const LANE: Readonly<Record<BoardLane, string>> = {
  backlog: "Backlog",
  ready: "Ready",
  in_progress: "In progress",
  in_review: "In review",
  blocked: "Blocked",
  complete: "Complete",
};

export function laneWord(lane: BoardLane): string {
  return LANE[lane];
}

/**
 * Priority, and the one place this page spends amber on data.
 *
 * `P0` is the only priority the record treats differently — it is operator
 * authority to raise one — so it is the only one drawn as a signal.
 */
export function PriorityChip({ priority }: { readonly priority: Priority }): ReactElement {
  return <Chip tone={priority === "P0" ? "amber" : "neutral"}>{priority}</Chip>;
}

/**
 * An instant, in UTC.
 *
 * Never the reader's locale: a recorded time is a fact about the record, and
 * two operators comparing screens must be reading the same number.
 */
export function Instant({ at }: { readonly at: string }): ReactElement {
  return (
    <Mono title={at} className="text-muted">
      {at.slice(0, 16).replace("T", " ")}Z
    </Mono>
  );
}

/** One labelled fact. The label is 12px muted; the value carries the weight. */
export function Fact({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="flex min-w-0 items-baseline gap-3 border-b border-line py-1.5 last:border-b-0">
      <span className="w-24 shrink-0 text-2xs text-muted">{label}</span>
      <span className="min-w-0 flex-1 text-sm break-words">{children}</span>
    </div>
  );
}

/** Nothing was recorded here. Said in words, never with a borrowed glyph. */
export function Unrecorded({ what }: { readonly what: string }): ReactElement {
  return <span className="text-sm text-muted">{what}</span>;
}

/**
 * The marks a card has earned, and only those.
 *
 * `⏸` is a blocker the record opened. `⚠` is a finding waiting on a person. A
 * card with neither draws neither: a state without a recorded fact draws no
 * mark at all.
 */
export function marksFor(card: BoardCard): readonly MarkName[] {
  const marks: MarkName[] = [];
  if (card.blocker_reason !== null) {
    marks.push("parked");
  }
  if (card.human_waiting.state === "waiting") {
    marks.push("warn");
  }
  return marks;
}

export function Marks({ card }: { readonly card: BoardCard }): ReactElement | null {
  const marks = marksFor(card);
  if (marks.length === 0) {
    return null;
  }
  return (
    <>
      {marks.map((name) => (
        <Mark key={name} name={name} />
      ))}
    </>
  );
}
