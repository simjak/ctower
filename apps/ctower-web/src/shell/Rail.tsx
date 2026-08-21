import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { destinationsIn, GROUPS } from "./destinations";
import type { Destination, DestinationKey } from "./destinations";

/**
 * The permanent rail. Five groups, every destination the product will have, and
 * an honest state on each.
 *
 * Three states, and they are different facts:
 *
 * - **here** — the destination you are on. Amber fill and an amber edge; this
 *   is the "active" the accent family exists for.
 * - **unbuilt** — the screen does not exist yet. Dimmed, not a link, and it
 *   says why on focus. It stays in the rail on purpose: an operator should
 *   learn a destination is empty before walking into it, not by arriving.
 * - **locked** — nothing is reachable, and the rail carries the reason rather
 *   than going quietly grey: on first run because no company exists yet, and
 *   while the company is being read because it is not yet known that one does.
 */
export function Rail({
  here,
  lockReason,
  onGo,
}: {
  readonly here: DestinationKey;
  readonly lockReason: string | null;
  readonly onGo: (key: DestinationKey) => void;
}): ReactElement {
  return (
    <nav
      aria-label="Sections"
      className="border-r border-line bg-[color-mix(in_srgb,var(--bg)_60%,var(--card))] py-3.5 max-md:hidden"
    >
      {GROUPS.map((group) => (
        <div key={group}>
          <div className="px-4 pt-3 pb-1 text-[10.5px] tracking-[0.1em] text-muted">{group}</div>
          {destinationsIn(group).map((destination) => (
            <RailLink
              key={destination.key}
              destination={destination}
              here={destination.key === here && lockReason === null}
              lockReason={lockReason}
              onGo={onGo}
            />
          ))}
        </div>
      ))}
    </nav>
  );
}

function RailLink({
  destination,
  here,
  lockReason,
  onGo,
}: {
  readonly destination: Destination;
  readonly here: boolean;
  readonly lockReason: string | null;
  readonly onGo: (key: DestinationKey) => void;
}): ReactElement {
  const reachable = destination.built && lockReason === null;
  const reason = lockReason ?? "Not built yet";

  return (
    <button
      type="button"
      disabled={!reachable}
      aria-current={here ? "page" : undefined}
      title={reachable ? undefined : reason}
      onClick={(): void => {
        onGo(destination.key);
      }}
      className={cn(
        "flex w-full items-center gap-2 px-4 py-1.5 text-left text-sm",
        here
          ? "border-r-2 border-amber bg-amber/14 font-semibold"
          : "border-r-2 border-transparent",
        reachable ? "cursor-pointer text-fg hover:bg-raised" : "cursor-default text-muted"
      )}
    >
      <span
        aria-hidden
        className={cn("size-[5px] shrink-0 rounded-full", here ? "bg-amber" : "bg-muted/50")}
      />
      <span className="truncate">{destination.label}</span>
      {reachable ? null : <span className="sr-only"> — {reason}</span>}
    </button>
  );
}
