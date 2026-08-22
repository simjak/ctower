import { useState } from "react";
import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { PageHead } from "../ui/primitives";
import { FilesPanel } from "./FilesPanel";
import { WorkspacesPanel } from "./WorkspacesPanel";

/**
 * The harness screen: where an operator sets the work up.
 *
 * The registry is a plain array so a panel is one line, and the panels are the
 * screen. Nothing here holds state on a panel's behalf.
 */
export interface HarnessTab {
  readonly key: string;
  readonly label: string;
  readonly element: ReactElement;
}

export const TABS: readonly HarnessTab[] = [
  { key: "files", label: "Agent files", element: <FilesPanel /> },
  { key: "workspaces", label: "Workspaces", element: <WorkspacesPanel /> },
];

export function HarnessPage(): ReactElement {
  const [here, setHere] = useState<string>(TABS[0]?.key ?? "");
  const open = TABS.find((tab) => tab.key === here) ?? TABS[0];

  return (
    <>
      <PageHead title="Harness" subtitle={<span>Set up the work this company runs.</span>} />
      <nav className="mb-4 flex items-center gap-1 border-b border-line">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            aria-current={tab.key === open?.key}
            onClick={(): void => {
              setHere(tab.key);
            }}
            className={cn(
              "-mb-px cursor-pointer border-b-2 px-3 py-2 text-sm",
              tab.key === open?.key
                ? "border-amber font-semibold text-fg"
                : "border-transparent text-muted hover:text-fg"
            )}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      {open?.element}
    </>
  );
}
