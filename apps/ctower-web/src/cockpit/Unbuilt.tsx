import type { ReactElement } from "react";
import { Hint } from "../ui/form";
import { cn } from "../ui/cn";

/**
 * A surface that does not exist yet, drawn honestly.
 *
 * `DESIGN.md`'s rule for a destination, applied to a pane: dimmed, "not built
 * yet", and the reason reachable — never a dead route and never a pretend page.
 * There is no mark, because a surface that does not exist is not in a state.
 *
 * The line is the fact. Why it is not built is rationale, and rationale never
 * renders by default: it sits behind the (i) disclosure, which a keyboard can
 * reach.
 */
export function Unbuilt({
  what,
  why,
  className,
}: {
  readonly what: string;
  readonly why: string;
  readonly className?: string;
}): ReactElement {
  return (
    <div className={cn("grid place-content-center p-6 text-center", className)}>
      <div className="max-w-[42ch]">
        <p className="m-0 text-sm font-medium text-muted">Not built yet</p>
        {/* The disclosure sits in the sentence's own flow, so a narrow pane
            wraps it with the words rather than stranding it on a line of its
            own at the far edge. */}
        <p className="mt-1 mb-0 text-xs text-balance text-muted">
          {what}{" "}
          <span className="inline-block translate-y-0.5">
            <Hint text={why} />
          </span>
        </p>
      </div>
    </div>
  );
}

/**
 * A control for a thing that is not built.
 *
 * Inert rather than `disabled`, so a keyboard still reaches it and still hears
 * the reason — the Rail settled this once already: a `disabled` control cannot
 * take focus, and a reason nobody can reach is not a reason.
 *
 * Unlike the Rail's rows, the tag is always drawn rather than revealed on
 * hover. A full-width bar at the foot of a conversation is the shape of a
 * composer, and a shape that says "type here" must carry its refusal where the
 * eye lands, not one interaction later.
 */
export function InertControl({
  label,
  reason,
  className,
}: {
  readonly label: string;
  readonly reason: string;
  readonly className?: string;
}): ReactElement {
  return (
    <button
      type="button"
      aria-disabled
      className={cn(
        "inline-flex shrink-0 cursor-default items-center justify-between gap-3 rounded-sm",
        "border border-dashed border-line bg-raised px-3 py-2 text-sm text-muted",
        className
      )}
    >
      <span>{label}</span>
      <span aria-hidden className="shrink-0 text-2xs">
        not built
      </span>
      <span className="sr-only"> — {reason}</span>
    </button>
  );
}
