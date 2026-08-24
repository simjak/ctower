import type { ReactElement, ReactNode } from "react";
import { cn } from "../ui/cn";

/**
 * An affordance the record cannot honour yet, drawn honestly.
 *
 * `DESIGN.md` already has this rule one level up: an unbuilt destination stays
 * in the rail, dimmed, not a link, with its reason on hover and on focus,
 * because an operator should learn a thing is empty before walking into it.
 * This is the same rule inside a screen — a field the reference console has and
 * a `ctower.project/v1` payload has nowhere to keep.
 *
 * It is deliberately not an input. A box someone can type into and whose words
 * go nowhere is worse than an absence: it takes an answer and drops it. This
 * takes nothing, says what it is, and keeps the shape of the screen the
 * operator asked for.
 */
export function Inert({
  reason,
  className,
  children,
}: {
  /** Why the record cannot hold this yet. One sentence. */
  readonly reason: string;
  readonly className?: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <span
      // Inert, not `disabled`. A disabled control cannot take focus, so a
      // keyboard could never reach the reason at all; `aria-disabled` keeps it
      // in the tab order and says it does not act.
      tabIndex={0}
      aria-disabled
      className={cn(
        // Dimmed and dashed. The rail dims an unbuilt destination and says why
        // on focus; a dashed edge is the same statement for something that has
        // an edge, so an operator reads "not yet" before they aim at it rather
        // than after they press it.
        "group relative cursor-default border-dashed text-muted/80",
        className
      )}
    >
      {children}
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute bottom-full left-0 z-50 mb-1.5 hidden w-max max-w-xs",
          "rounded-md border border-line bg-card px-2.5 py-1.5 text-2xs text-fg",
          "group-hover:block group-focus-visible:block"
        )}
      >
        {reason}
      </span>
      <span className="sr-only"> — {reason}</span>
    </span>
  );
}
