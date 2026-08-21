import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { Mark } from "../ui/marks";
import type { Step, StepKey } from "./steps";

type Position = "done" | "here" | "ahead";

/**
 * The four steps of the Company page, drawn once, across the top.
 *
 * Each is named as a job the operator does and carries nothing else: no call,
 * no code, no explanation. They run horizontally because the shell already owns
 * a vertical rail, and a screen with two of those tells the operator that
 * neither is the way out.
 *
 * Progress is the amber ramp: the step you are on is amber, a step behind you
 * carries the CLI's own done mark, a step ahead is quiet.
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
    <nav aria-label="Steps" className="mb-5 border-b border-line">
      <ol className="m-0 flex list-none gap-1 p-0">
        {steps.map((step, index) => (
          <li key={step.key}>
            <RailStep step={step} position={positionOf(index, here, furthest)} />
          </li>
        ))}
      </ol>
    </nav>
  );
}

function RailStep({
  step,
  position,
}: {
  readonly step: Step;
  readonly position: Position;
}): ReactElement {
  return (
    <div
      aria-current={position === "here" ? "step" : undefined}
      className={cn(
        "flex items-center gap-2 border-b-2 px-3 py-2 text-sm",
        position === "here" ? "border-amber font-semibold text-fg" : "border-transparent text-muted"
      )}
    >
      {position === "done" ? (
        <Mark name="done" />
      ) : (
        <span
          aria-hidden
          className={cn(
            "mono inline-block w-[1.4em] shrink-0",
            position === "here" ? "text-amber" : ""
          )}
        >
          {step.ordinal}
        </span>
      )}
      <span className="truncate">{step.label}</span>
    </div>
  );
}

function positionOf(index: number, here: number, furthest: number): Position {
  if (index === here) {
    return "here";
  }
  return index <= furthest ? "done" : "ahead";
}
