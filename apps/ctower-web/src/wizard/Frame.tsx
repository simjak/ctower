import type { ReactElement, ReactNode } from "react";
import { StepRail } from "./StepRail";
import { STEPS } from "./steps";
import type { StepKey } from "./steps";

/**
 * The page's own body: the four steps across the top, the step under them, and
 * the one control that leaves it.
 *
 * The steps run horizontally now because the shell already owns a vertical rail
 * and a screen with two of them tells the operator neither is the way out.
 */
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
    <>
      <StepRail steps={STEPS} current={current} reached={reached} />
      <div className="min-w-0" aria-live="polite">
        {children}
        {footer === undefined ? null : (
          <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
            {footer}
          </footer>
        )}
      </div>
    </>
  );
}
