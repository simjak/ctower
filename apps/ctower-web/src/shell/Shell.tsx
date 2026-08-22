import type { ReactElement, ReactNode } from "react";
import { cn } from "../ui/cn";
import { ThemeToggle } from "../app/ThemeToggle";
import { OrgSwitcher } from "./OrgSwitcher";
import type { Org } from "./OrgSwitcher";
import { Rail } from "./Rail";
import type { DestinationKey } from "./destinations";

/**
 * One app, one shell. A 200px rail and fluid content, capped at 1200 — the
 * grid `DESIGN.md` fixes, desktop-first, because this is a daily-driver console
 * and not a page that has to survive a phone.
 */
export function Shell({
  here,
  lockReason,
  onGo,
  org,
  status,
  fill = false,
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
      <div className="grid min-h-[calc(100dvh-52px)] md:grid-cols-[200px_minmax(0,1fr)]">
        <div className="border-r border-line bg-[color-mix(in_srgb,var(--bg)_60%,var(--card))] max-md:hidden">
          {org === null ? null : (
            <div className="border-b border-line">
              <OrgSwitcher org={org} />
            </div>
          )}
          <Rail here={here} lockReason={lockReason} onGo={onGo} />
        </div>
        <main className="min-w-0">
          <div
            className={cn(
              "mx-auto flex max-w-[1200px] flex-col px-6 py-5",
              fill && "h-[calc(100dvh-52px)]"
            )}
          >
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
