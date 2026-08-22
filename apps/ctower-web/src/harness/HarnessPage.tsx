import { Tabs } from "radix-ui";
import type { ReactElement } from "react";
import { PageHead } from "../ui/primitives";
import { cn } from "../ui/cn";
import { EMPTY_TEMPLATE } from "../wizard/bundle";
import type { Seed } from "../wizard/useSeed";
import { CrewPanel } from "./CrewPanel";

/**
 * The harness screen: where an operator sets the work up.
 *
 * The registry is a plain array so a new panel is one line. Each entry is a key,
 * the operator's word for the job, and the panel that answers on it — nothing
 * here knows what any panel does.
 *
 * The list is a real tab list rather than styled buttons, so the arrow keys walk
 * it and the one focus treatment the token layer puts on everything focusable
 * lands where it should.
 */
export interface HarnessTab {
  readonly key: string;
  readonly label: string;
  readonly element: ReactElement;
}

export function HarnessPage({
  seed,
  onApplied,
}: {
  readonly seed: Seed;
  readonly onApplied: () => void;
}): ReactElement {
  const bundle = seed.kind === "exported" ? seed.result.bundle : EMPTY_TEMPLATE;
  const tabs: readonly HarnessTab[] = [
    { key: "crew", label: "Crew", element: <CrewPanel recorded={bundle} onRecorded={onApplied} /> },
  ];
  const first = tabs[0];

  return (
    <>
      <PageHead title="Harness" subtitle={<span>Set up the work this company runs.</span>} />
      {first === undefined ? null : (
        <Tabs.Root defaultValue={first.key}>
          <Tabs.List className="mb-4 flex items-center gap-1 border-b border-line">
            {tabs.map((tab) => (
              <Tabs.Trigger
                key={tab.key}
                value={tab.key}
                className={cn(
                  "-mb-px cursor-pointer border-0 border-b-2 border-transparent bg-transparent",
                  "px-3 py-2 text-sm font-medium text-muted",
                  "data-[state=active]:border-amber data-[state=active]:text-fg"
                )}
              >
                {tab.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>
          {tabs.map((tab) => (
            <Tabs.Content key={tab.key} value={tab.key}>
              {tab.element}
            </Tabs.Content>
          ))}
        </Tabs.Root>
      )}
    </>
  );
}
