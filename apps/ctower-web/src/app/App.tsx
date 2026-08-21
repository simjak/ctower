import type { ReactElement } from "react";
import { TooltipScope } from "../ui/form";
import { Wizard } from "../wizard/Wizard";
import { ThemeToggle } from "./ThemeToggle";

/**
 * One screen. The company-creation wizard is the whole of this application:
 * there is no navigation, no second route, and no chrome around it that leads
 * anywhere else.
 */
export function App(): ReactElement {
  return (
    <TooltipScope>
      <div className="min-h-dvh bg-bg text-ink">
        <header className="flex h-12 items-center gap-2 border-b border-line bg-surface px-6">
          <span className="text-sm font-semibold tracking-[-0.01em] text-ink">ctower</span>
          <span aria-hidden className="text-ink-4">
            /
          </span>
          <span className="text-sm text-ink-2">Create a company</span>
          <span className="flex-1" />
          <ThemeToggle />
        </header>
        <Wizard />
      </div>
    </TooltipScope>
  );
}
