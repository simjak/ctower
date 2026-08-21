import { Check } from "lucide-react";
import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import type { Step, StepKey } from "./steps";

type Mark = "done" | "here" | "ahead";

/**
 * The four steps, drawn once. Each one is named as a job the operator does, and
 * carries nothing else: no call, no code, no explanation of what the step is
 * for. A step that needs a sentence to justify itself is a step in the wrong
 * place.
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
    <nav aria-label="Steps">
      <ol className="m-0 flex list-none gap-0.5 p-0 md:flex-col">
        {steps.map((step, index) => (
          <li key={step.key} className="min-w-0 flex-1">
            <RailStep step={step} mark={markOf(index, here, furthest)} />
          </li>
        ))}
      </ol>
    </nav>
  );
}

function RailStep({ step, mark }: { readonly step: Step; readonly mark: Mark }): ReactElement {
  return (
    <div
      aria-current={mark === "here" ? "step" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-2.5 py-2",
        "transition-colors duration-(--motion-duration-fast)",
        mark === "here" ? "bg-raised" : ""
      )}
    >
      <span
        aria-hidden
        className={cn(
          "grid size-5 shrink-0 place-content-center rounded-full border text-[11px] font-medium",
          mark === "done" ? "border-proven bg-proven text-white" : "",
          mark === "here" ? "border-accent bg-accent text-white" : "",
          mark === "ahead" ? "border-line-2 text-ink-4" : ""
        )}
      >
        {mark === "done" ? <Check className="size-3" strokeWidth={3} /> : step.ordinal}
      </span>
      <span
        className={cn(
          "truncate text-[13px]",
          mark === "here" ? "font-semibold text-ink" : "text-ink-2"
        )}
      >
        {step.label}
      </span>
    </div>
  );
}

function markOf(index: number, here: number, furthest: number): Mark {
  if (index === here) {
    return "here";
  }
  return index <= furthest ? "done" : "ahead";
}
