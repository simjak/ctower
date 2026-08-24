import { ChevronLeft, Folder } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { cn } from "../../ui/cn";
import { Button, Chip } from "../../ui/primitives";
import { Shell } from "../../shell/Shell";
import { ProjectSwitcher } from "../../shell/ProjectSwitcher";
import { COMPANY, HERE, PROJECTS } from "./fixtures";

/**
 * The real shell and the real project head, around a tab that is not wired.
 *
 * The rail, the company switcher and the project dropdown are the app's own
 * components taking fixture props — nothing here is a drawing of them. So the
 * mock sits at the width, under the header and beside the navigation the
 * operator actually gets, and a judgement made on the bench holds for the
 * screen.
 *
 * The first tab reads **Tickets**. It said Tasks when this screen landed;
 * T-027's frozen spec fixes the product on one noun, and a bench that still
 * said Tasks would be showing a screen nobody is going to build.
 */
export function Frame({ children }: { readonly children: ReactNode }): ReactElement {
  return (
    <Shell
      here="tickets"
      lockReason={null}
      onGo={(): void => undefined}
      org={{ name: COMPANY, key: "manibo" }}
      project={
        <ProjectSwitcher
          projects={PROJECTS}
          current={HERE}
          onChoose={(): void => undefined}
          onAdd={(): void => undefined}
        />
      }
    >
      <nav aria-label="Trail" className="mb-3 flex items-center gap-1.5 text-2xs text-muted">
        <Button variant="quiet" size="sm" className="-ml-2.5">
          <ChevronLeft /> Projects
        </Button>
        <span aria-hidden>›</span>
        <span className="truncate text-fg">{HERE.name}</span>
      </nav>

      <header className="mb-4 flex flex-wrap items-center gap-3">
        <Folder aria-hidden className="size-5 shrink-0 text-muted" />
        <h1 className="m-0 min-w-0 flex-1 truncate text-xl leading-tight font-bold tracking-[-0.02em]">
          {HERE.name}
        </h1>
        <Chip>{HERE.prefix}</Chip>
      </header>

      <div role="tablist" aria-label="Project" className="mb-4 flex gap-1 border-b border-line">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={tab === "Configuration"}
            className={cn(
              "-mb-px cursor-pointer border-b-2 px-3 py-2 text-sm",
              tab === "Configuration"
                ? "border-amber font-semibold text-fg"
                : "border-transparent text-muted hover:bg-raised hover:text-fg"
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {children}
    </Shell>
  );
}

const TABS: readonly string[] = ["Tickets", "Overview", "Configuration", "Budget"];
