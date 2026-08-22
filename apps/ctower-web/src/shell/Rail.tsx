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
 * - **here** — the destination you are on. A soft neutral fill and a thin left
 *   accent, which is what the reference's resting active row is. It was an
 *   amber fill and an amber right edge until 2026-08-22; amber at rest is the
 *   one thing the reference's palette has no counterpart for, and this rail is
 *   now the Cockpit's rail. Amber survives here as the focus ring and nothing
 *   else — that is `app.css`, on every focusable, unchanged.
 * - **unbuilt** — the screen does not exist yet. Dimmed, not a link, and it
 *   says why on focus. It stays in the rail on purpose: an operator should
 *   learn a destination is empty before walking into it, not by arriving.
 * - **locked** — nothing is reachable, and the rail carries the reason rather
 *   than going quietly grey: on first run because no company exists yet, and
 *   while the company is being read because it is not yet known that one does.
 */
/**
 * A section heading inside the rail. Exported because the open screen's own
 * block sits in this same column and has to be labelled the same way — one rail
 * with two label styles would read as two rails that failed to merge.
 */
export const RAIL_SECTION = "px-4 pt-3 pb-1 text-[10.5px] tracking-[0.1em] text-muted";

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
    <nav aria-label="Sections" className="py-3.5">
      {GROUPS.map((group) => (
        <div key={group}>
          <div className={RAIL_SECTION}>{group}</div>
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
  const short = lockReason === null ? "not built" : "locked";

  return (
    <button
      type="button"
      // Inert, not `disabled`. A disabled button cannot take hover or focus, so
      // its native `title` had nothing to anchor to and Chromium drew it at the
      // corner of the viewport — and a keyboard could never reach the reason at
      // all, which the law asks for by name. `aria-disabled` keeps the control
      // in the tab order and says it does not act.
      aria-disabled={reachable ? undefined : true}
      aria-current={here ? "page" : undefined}
      onClick={(): void => {
        if (reachable) {
          onGo(destination.key);
        }
      }}
      className={cn(
        "group flex w-full items-center gap-1.5 px-4 py-1.5 text-left text-sm",
        here ? "border-l-2 border-fg/30 bg-raised font-medium" : "border-l-2 border-transparent",
        reachable ? "cursor-pointer text-fg hover:bg-raised" : "cursor-default text-muted"
      )}
    >
      {/* A 16px slot, so this block's labels sit in the same column as the
          seat tree's below the divider. One rail, one label grid. */}
      <span aria-hidden className="grid size-4 shrink-0 place-content-center">
        <span className={cn("size-[5px] rounded-full", here ? "bg-fg" : "bg-muted/50")} />
      </span>
      <span className="truncate">{destination.label}</span>
      {reachable ? null : (
        <>
          {/* The reason, in the row the eye is already on, on hover and on
              focus. Not a floating tooltip: there is nothing to mis-position. */}
          <span
            aria-hidden
            className="ml-auto hidden shrink-0 text-2xs text-muted group-hover:inline group-focus-visible:inline"
          >
            {short}
          </span>
          <span className="sr-only"> — {reason}</span>
        </>
      )}
    </button>
  );
}
