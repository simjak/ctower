import { ArrowUp } from "lucide-react";
import type { ReactElement } from "react";
import { Hint } from "../ui/form";
import { cn } from "../ui/cn";

const COMPOSER_REASON =
  "Composer send is authored as one typed operator command with no implementation at this head.";
const STEER_REASON =
  "Steer is authored as the same typed command path as send, with no implementation at this head.";

/**
 * A surface that does not exist yet, drawn honestly in the reference's own
 * quiet: muted type, centred, no border and no fill of its own.
 *
 * The rule for a destination applied to a pane — "not built yet" and the reason
 * reachable, never a dead route and never a pretend page. There is no mark,
 * because a surface that does not exist is not in a state. The line is the
 * fact; why it is not built is rationale, and rationale lives behind the (i),
 * which a keyboard can reach.
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
 * The composer, in the reference's geometry and inert.
 *
 * Measured off `crop-composer.png`: one rounded box at radius 12, a 150px
 * height, 16px padding, and an integrated toolbar along its bottom edge rather
 * than controls set beside an input.
 *
 * What the box says is the one thing that differs, and it differs on purpose. A
 * placeholder that reads like an invitation to type is the one thing an
 * operator console may never draw over a surface that cannot send, so the box
 * carries its own refusal where the eye lands first — at rest, not on hover.
 * The model chip the reference puts in the toolbar is omitted: `model_ref` is
 * real per session, but no session is bound to a composer, so a chip here would
 * name a model nothing is about to use.
 */
export function Composer(): ReactElement {
  return (
    <div className="rounded-[12px] border border-line bg-[color-mix(in_srgb,var(--fg)_2%,transparent)] p-4">
      <div className="flex h-[86px] flex-col">
        <p className="m-0 flex items-start gap-1.5 text-sm text-muted">
          Sending a message to a crew is not built yet.
          <span className="inline-block translate-y-0.5">
            <Hint text={COMPOSER_REASON} />
          </span>
        </p>
      </div>
      <div className="flex items-center gap-3">
        <InertAction label="Steer" reason={STEER_REASON} />
        <span className="flex-1" />
        <span aria-hidden className="text-2xs text-muted">
          not built
        </span>
        <button
          type="button"
          aria-disabled
          aria-label="Send — not built yet"
          className="grid size-6.5 cursor-default place-content-center rounded-sm bg-raised text-muted"
        >
          <ArrowUp aria-hidden className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

/**
 * A control for a thing that is not built. Inert rather than `disabled`, so a
 * keyboard still reaches it and still hears the reason — a `disabled` control
 * cannot take focus, and a reason nobody can reach is not a reason.
 */
function InertAction({
  label,
  reason,
}: {
  readonly label: string;
  readonly reason: string;
}): ReactElement {
  return (
    <button
      type="button"
      aria-disabled
      className="cursor-default rounded-sm px-1.5 py-0.5 text-xs text-muted"
    >
      {label}
      <span className="sr-only"> — not built yet. {reason}</span>
    </button>
  );
}
