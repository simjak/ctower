import type { ReactElement, ReactNode } from "react";
import { cn } from "../ui/cn";
import { ThemeToggle } from "../app/ThemeToggle";
import { OrgSwitcher } from "./OrgSwitcher";
import type { Org } from "./OrgSwitcher";
import { Rail } from "./Rail";
import type { DestinationKey } from "./destinations";

/**
 * One app, one shell, and **one rail**.
 *
 * The rail is 248 and it carries two blocks: this app's destinations, then
 * whatever the open screen contributes under a full-bleed divider. That is the
 * reference's own column — `Home`/`Create`/`Search` above `Pinned`/`My
 * workspaces`/`Team` — and it replaces the two-rail arrangement this shell had
 * until 2026-08-22. A second rail beside the first was never the reference's
 * answer to carrying navigation and a list at once; one column with section
 * headings is.
 *
 * Content is fluid under it: a page caps at `DESIGN.md`'s 1200, and a workspace
 * caps at the frame that makes its panes measure 1200 exactly.
 */
export function Shell({
  here,
  lockReason,
  onGo,
  org,
  status,
  fill = false,
  rail,
  children,
}: {
  readonly here: DestinationKey;
  /** Why nothing is reachable, when nothing is. */
  readonly lockReason: string | null;
  readonly onGo: (key: DestinationKey) => void;
  /** The company this console is looking at, once it is known. */
  readonly org: Org | null;
  readonly status?: ReactNode;
  /**
   * A workspace rather than a page: it takes the height of the viewport and
   * scrolls inside its own panes. A page keeps the ordinary flow, where the
   * document is as long as it needs to be.
   */
  readonly fill?: boolean;
  /**
   * What the open screen puts in the rail under the destinations. Content, not
   * navigation — it changes with the screen, while the destinations above it
   * never do.
   */
  readonly rail?: ReactNode;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="min-h-dvh bg-bg text-fg">
      <header className="sticky top-0 z-10 border-b border-line bg-bg">
        <div className="flex h-13 items-center gap-3 px-4">
          <span className="text-md font-semibold">
            c<span className="text-amber">tower</span>
          </span>
          {status}
          <span className="flex-1" />
          <ThemeToggle />
        </div>
      </header>
      <div className="grid min-h-[calc(100dvh-52px)] md:grid-cols-[248px_minmax(0,1fr)]">
        {/* One column, so it owns its own scroll: nine destinations and a
            company's seats together outrun the viewport, and a rail that pushes
            the page taller instead of scrolling itself is how the item list
            ends up unreachable. */}
        <div className="sticky top-13 flex h-[calc(100dvh-52px)] flex-col overflow-y-auto border-r border-line bg-[color-mix(in_srgb,var(--bg)_60%,var(--card))] max-md:hidden">
          {org === null ? null : (
            <div className="border-b border-line">
              <OrgSwitcher org={org} />
            </div>
          )}
          <Rail here={here} lockReason={lockReason} onGo={onGo} />
          {rail === undefined ? null : <div className="border-t border-line">{rail}</div>}
        </div>
        <main className="min-w-0">
          <div
            className={cn(
              "mx-auto flex flex-col px-6 py-5",
              // A workspace owns the viewport and scrolls inside its own panes.
              // Without the clip here the panes still clip visually, but the
              // document itself stays scrollable and the operator can drag the
              // whole console up into blank space below it.
              //
              // Its cap is 1250 rather than a page's 1200 because the measured
              // spec's 1200 is the *panes*: 1200 + the frame's two 1px rules +
              // two 24px gutters. A page's 1200 is the page.
              fill ? "h-[calc(100dvh-52px)] max-w-[1250px] overflow-hidden" : "max-w-[1200px]"
            )}
          >
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
