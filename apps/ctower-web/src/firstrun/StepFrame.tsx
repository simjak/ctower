import { ArrowLeft, ArrowRight } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { Button } from "../ui/primitives";
import { cn } from "../ui/cn";

/**
 * One question, full screen.
 *
 * The reference console's structure exactly: thin progress bars over an icon tile, a big
 * title, one line under it, the question, and an obvious way forward. The skin
 * is ctower's — the filled bars are the amber ramp, the primary is the amber
 * fill, and nothing moves.
 */
export function StepFrame({
  step,
  total,
  icon,
  title,
  lead,
  children,
  onBack,
  onNext,
  nextLabel,
  nextReady,
  onSkip,
  skipLabel,
  action,
}: {
  readonly step: number;
  readonly total: number;
  readonly icon: ReactNode;
  readonly title: string;
  readonly lead: ReactNode;
  readonly children: ReactNode;
  readonly onBack?: (() => void) | undefined;
  readonly onNext: () => void;
  readonly nextLabel: string;
  readonly nextReady: boolean;
  readonly onSkip?: (() => void) | undefined;
  readonly skipLabel?: string | undefined;
  /** A control this step owns whose meaning belongs to the form inside it. */
  readonly action?: ReactNode;
}): ReactElement {
  return (
    <div className="mx-auto w-[min(640px,100%)] px-6 py-16">
      <ol
        className="m-0 mb-10 flex list-none gap-2 p-0"
        aria-label={`Step ${String(step)} of ${String(total)}`}
      >
        {Array.from({ length: total }, (_, index) => (
          <li
            key={index}
            className={cn("h-[3px] flex-1 rounded-full", index < step ? "bg-amber" : "bg-line")}
          />
        ))}
      </ol>

      <div className="flex items-start gap-4">
        <span
          aria-hidden
          className="grid size-10 shrink-0 place-content-center rounded-sm bg-raised text-muted"
        >
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <h1 className="m-0 text-xl leading-tight font-bold tracking-[-0.02em]">{title}</h1>
          <p className="mt-1 mb-0 text-sm text-muted">{lead}</p>
        </div>
        {action === undefined ? null : <div className="shrink-0">{action}</div>}
      </div>

      <div className="mt-8">{children}</div>

      <div className="mt-10 flex items-center gap-3">
        {onBack === undefined ? (
          <span className="flex-1" />
        ) : (
          <>
            <Button variant="quiet" onClick={onBack}>
              <ArrowLeft /> Back
            </Button>
            <span className="flex-1" />
          </>
        )}
        {onSkip === undefined || skipLabel === undefined ? null : (
          <Button variant="quiet" onClick={onSkip}>
            {skipLabel}
          </Button>
        )}
        <Button variant="primary" disabled={!nextReady} onClick={onNext}>
          {nextLabel} <ArrowRight />
        </Button>
      </div>
    </div>
  );
}
