import type { ReactElement, ReactNode } from "react";
import { StepRail } from "./StepRail";
import { STEPS } from "./steps";
import type { StepKey } from "./steps";

/** The rail, the content column, and nothing else. */
export function Frame({
  current,
  reached,
  children,
  footer,
}: {
  readonly current: StepKey;
  readonly reached: StepKey;
  readonly children: ReactNode;
  readonly footer?: ReactNode;
}): ReactElement {
  return (
    <div className="mx-auto grid max-w-[1000px] gap-8 px-6 py-8 md:grid-cols-[180px_minmax(0,1fr)]">
      <StepRail steps={STEPS} current={current} reached={reached} />
      <div className="min-w-0" aria-live="polite">
        {children}
        {footer === undefined ? null : (
          <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
