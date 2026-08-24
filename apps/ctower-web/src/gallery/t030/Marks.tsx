import type { ReactElement, ReactNode } from "react";
import { cn } from "../../ui/cn";
import { Chip } from "../../ui/primitives";
import { LEGEND, MARK_LABEL, WHY } from "./fixtures";
import type { Disposition } from "./fixtures";

/**
 * The annotation layer, and it is a layer on purpose.
 *
 * Nothing in this file ships. It exists so one screen can answer two different
 * questions at two different addresses — *what should this be* and *what is
 * each row waiting on* — without the second question's vocabulary leaking into
 * the first. `schema`, `export`, `lifecycle` are exactly the machine words the
 * operator's standing rule keeps off a rendered surface, so they render here,
 * on the bench, addressed to the engineer who has to move the contract, and
 * never on the tab.
 */
const TONE: Readonly<Record<Disposition, "ok" | "amber" | "danger" | "neutral">> = {
  "record-backed": "ok",
  // A field the record refuses is refused, and `danger` is this system's word
  // for refused. It is the strongest mark on the sheet because it is the only
  // one that stops a row from rendering at all.
  "needs-schema": "danger",
  "needs-read": "amber",
  "needs-ceremony": "neutral",
};

export function Mark({
  mark,
  why,
  on,
}: {
  readonly mark: Disposition;
  /** The key in `WHY` — the field's own name in the record, or the proposal. */
  readonly why: string;
  /** Whether the annotation layer is drawn at all. */
  readonly on: boolean;
}): ReactElement | null {
  if (!on) {
    return null;
  }
  return (
    <span className="flex shrink-0 items-center gap-2">
      <span className="text-2xs text-muted italic">{WHY[why]}</span>
      <Chip tone={TONE[mark]}>{MARK_LABEL[mark]}</Chip>
    </span>
  );
}

/** What the four marks mean and who each one is addressed to. */
export function Legend(): ReactElement {
  return (
    <div className="mb-4 rounded-md border border-dashed border-line bg-raised px-4 py-3">
      <p className="m-0 mb-2 text-2xs font-semibold tracking-[0.06em] text-muted uppercase">
        How each row is missing
      </p>
      <ul className="m-0 grid list-none gap-1.5 p-0 sm:grid-cols-2">
        {LEGEND.map((entry) => (
          <li key={entry.mark} className="flex items-baseline gap-2">
            <Chip tone={TONE[entry.mark]} className="shrink-0">
              {MARK_LABEL[entry.mark]}
            </Chip>
            <span className="text-2xs text-muted">{entry.means}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * One labeled row of the Configuration tab.
 *
 * The reference's shape: a fixed label column, the value filling the rest. The
 * mark, when the annotation layer is on, sits at the far right so the value
 * column stays the same width in both views and the two screenshots can be laid
 * over each other.
 */
export function Row({
  label,
  mark,
  tall = false,
  children,
}: {
  readonly label: string;
  readonly mark?: ReactNode;
  /**
   * Whether the value is taller than a line. A label baseline-aligned against a
   * two-line box lands at the bottom of it, which reads as a caption under the
   * field rather than a name for it, so a tall row aligns to the top instead.
   */
  readonly tall?: boolean;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div
      className={cn(
        "flex flex-wrap gap-x-4 gap-y-1.5 border-b border-line py-2.5 last:border-b-0",
        tall ? "items-start" : "items-baseline"
      )}
    >
      <span className={cn("w-32 shrink-0 text-2xs text-muted", tall && "pt-2.5")}>{label}</span>
      <span className="min-w-0 flex-1 text-sm text-fg">{children}</span>
      {mark}
    </div>
  );
}
