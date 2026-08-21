import type { ReactElement } from "react";
import type { Step, StepKey } from "./steps";

type Mark = "done" | "here" | "ahead";

/**
 * The four steps, drawn once, as a rail.
 *
 * The mark is `ctowerctl`'s own: `●` for a step that answered, `⟳` for the one
 * in flight, `○` for one not reached. The word beside it names the step, never
 * the state — the rail is its own legend, so the glyph carries the state and it
 * is not spelled out four times (D9).
 */
export function StepRail({
  steps,
  current,
  reached,
}: {
  readonly steps: readonly Step[];
  readonly current: StepKey;
  readonly reached: StepKey;
}): ReactElement {
  const here = steps.findIndex((step) => step.key === current);
  const furthest = steps.findIndex((step) => step.key === reached);

  return (
    <ol className="m-0 flex list-none gap-1 p-0 md:flex-col" aria-label="Steps">
      {steps.map((step, index) => (
        <li key={step.key} className="min-w-0 flex-1">
          <RailStep step={step} mark={markOf(index, here, furthest)} here={index === here} />
        </li>
      ))}
    </ol>
  );
}

const GLYPH: Readonly<Record<Mark, string>> = { done: "●", here: "⟳", ahead: "○" };
const GLYPH_INK: Readonly<Record<Mark, string>> = {
  done: "text-proven",
  here: "text-accent",
  ahead: "text-ink-4",
};

function RailStep({
  step,
  mark,
  here,
}: {
  readonly step: Step;
  readonly mark: Mark;
  readonly here: boolean;
}): ReactElement {
  return (
    <div
      aria-current={here ? "step" : undefined}
      className={`flex items-baseline gap-2 rounded-md border px-2.5 py-1.5 ${
        here ? "border-line-2 bg-surface-2" : "border-transparent"
      }`}
    >
      <span aria-hidden className={`text-[11px] leading-none ${GLYPH_INK[mark]}`}>
        {GLYPH[mark]}
      </span>
      <div className="min-w-0 flex-1">
        <div className={`text-[13px] ${here ? "font-semibold text-ink" : "text-ink-2"}`}>
          {step.label}
          <span className="sr-only"> — {mark}</span>
        </div>
        <div className="mono hidden truncate text-ink-4 md:block" title={step.operation}>
          {step.operation}
        </div>
      </div>
    </div>
  );
}

function markOf(index: number, here: number, furthest: number): Mark {
  if (index === here) {
    return "here";
  }
  return index <= furthest ? "done" : "ahead";
}
