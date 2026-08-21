import type { ReactElement } from "react";
import { Wizard } from "../wizard/Wizard";
import { ThemeToggle } from "./ThemeToggle";

/**
 * One screen. The company-creation wizard is the whole of this application:
 * there is no navigation, no second route, and no chrome around it that leads
 * anywhere else.
 */
export function App(): ReactElement {
  return (
    <div className="min-h-dvh bg-bg text-ink">
      <header className="flex h-[46px] items-center gap-2 border-b border-line bg-surface px-4">
        <span className="text-[13px] font-semibold tracking-[0.02em]">Create a company</span>
        <span className="flex-1" />
        <ThemeToggle />
      </header>
      <Wizard />
    </div>
  );
}
