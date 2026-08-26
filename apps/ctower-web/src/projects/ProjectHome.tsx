import { useState } from "react";
import { ChevronLeft, Folder } from "lucide-react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { cn } from "../ui/cn";
import { Button, Chip } from "../ui/primitives";
import { Budget } from "./home/Budget";
import { Configuration } from "./home/Configuration";
import { Overview } from "./home/Overview";
import { Tasks } from "./home/Tasks";
import type { ProjectFacts } from "./read";

/**
 * One project's own screen: the tickets on it, what the company records under
 * it, what it is configured as, and what it costs.
 *
 * Four tabs, and they are four different questions. Tickets opens first because
 * it is the one an operator arrives with — this is the project's tickets read,
 * the same record the Board serves, presented as the list you work down and as
 * the columns you scan. The tab is named for the one noun this product uses;
 * "Tasks" was a word from the reference console and named nothing here.
 *
 * A tab is a place inside a screen and not a screen of its own, so it does not
 * enter the address: the address says which project, and the rail says which
 * workspace. What survives a reload is the project.
 *
 * The rail's Tickets opens this screen on Tasks, so the tab bar is the local
 * navigation of one destination rather than a second navigation system beside
 * the rail. Which tab it opens on is the caller's, for that reason.
 */
export function ProjectHome({
  project,
  document,
  opensOn = "tickets",
  onBack,
  onOpenTicket,
}: {
  readonly project: ProjectFacts;
  /** The company record the tickets tab draws its people and projects from. */
  readonly document: CompanyBundleDocument;
  /** The tab the screen opens on; the operator moves it from there. */
  readonly opensOn?: TabKey;
  /** Where the trail goes back to. */
  readonly onBack: () => void;
  readonly onOpenTicket: (ticketId: string) => void;
}): ReactElement {
  const [here, setHere] = useState<TabKey>(opensOn);

  return (
    <>
      <nav aria-label="Trail" className="mb-3 flex items-center gap-1.5 text-2xs text-muted">
        <Button variant="quiet" size="sm" className="-ml-2.5" onClick={onBack}>
          <ChevronLeft /> Projects
        </Button>
        <span aria-hidden>›</span>
        <span className="truncate text-fg">{project.name}</span>
      </nav>

      <header className="mb-4 flex flex-wrap items-center gap-3">
        <Folder aria-hidden className="size-5 shrink-0 text-muted" />
        <h1 className="m-0 min-w-0 flex-1 truncate text-xl leading-tight font-bold tracking-[-0.02em]">
          {project.name}
        </h1>
        {project.prefix === null ? null : <Chip>{project.prefix}</Chip>}
      </header>

      <div role="tablist" aria-label="Project" className="mb-4 flex gap-1 border-b border-line">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={tab.key === here}
            onClick={(): void => {
              setHere(tab.key);
            }}
            className={cn(
              "-mb-px cursor-pointer border-b-2 px-3 py-2 text-sm",
              tab.key === here
                ? "border-amber font-semibold text-fg"
                : "border-transparent text-muted hover:bg-raised hover:text-fg"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Panel here={here} project={project} document={document} onOpenTicket={onOpenTicket} />
    </>
  );
}

export type TabKey = "tickets" | "overview" | "configuration" | "budget";

const TABS: readonly { readonly key: TabKey; readonly label: string }[] = [
  { key: "tickets", label: "Tickets" },
  { key: "overview", label: "Overview" },
  { key: "configuration", label: "Configuration" },
  { key: "budget", label: "Budget" },
];

function Panel({
  here,
  project,
  document,
  onOpenTicket,
}: {
  readonly here: TabKey;
  readonly project: ProjectFacts;
  readonly document: CompanyBundleDocument;
  readonly onOpenTicket: (ticketId: string) => void;
}): ReactElement {
  switch (here) {
    case "tickets":
      return <Tasks project={project} document={document} onOpen={onOpenTicket} />;
    case "overview":
      return <Overview project={project} />;
    case "configuration":
      return <Configuration project={project} />;
    case "budget":
      return <Budget />;
  }
}
