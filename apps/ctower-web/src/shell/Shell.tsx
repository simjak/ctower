import type { ReactElement, ReactNode } from "react";
import { ThemeToggle } from "../app/ThemeToggle";
import { Chip } from "../ui/primitives";
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
  status,
  children,
}: {
  readonly here: DestinationKey;
  /** Why nothing is reachable, when nothing is. */
  readonly lockReason: string | null;
  readonly onGo: (key: DestinationKey) => void;
  readonly status?: ReactNode;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="min-h-dvh bg-bg text-fg">
      <header className="sticky top-0 z-10 border-b border-line bg-bg">
        <div className="flex h-13 items-center gap-3 px-4">
          <span className="text-md font-semibold">
            c<span className="text-amber">tower</span>
          </span>
          {lockReason === null ? null : <Chip>first run</Chip>}
          {status}
          <span className="flex-1" />
          <ThemeToggle />
        </div>
      </header>
      <div className="grid min-h-[calc(100dvh-52px)] md:grid-cols-[200px_minmax(0,1fr)]">
        <Rail here={here} lockReason={lockReason} onGo={onGo} />
        <main className="min-w-0">
          <div className="mx-auto max-w-[1200px] px-6 py-5">{children}</div>
        </main>
      </div>
    </div>
  );
}
