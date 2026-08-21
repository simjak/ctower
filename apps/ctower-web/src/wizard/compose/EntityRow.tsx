import { Minus, Undo2 } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Chip, Mono } from "../../ui/primitives";
import { cn } from "../../ui/cn";
import type { EntityFact } from "../read";

/**
 * One project or one agent.
 *
 * Taking something out of a company is not a filter, and it was drawn as one: a
 * checkbox reads as "show me this", and what it actually meant was "retire this
 * on apply". So the control is now an explicit `Remove`, everything is kept
 * until the operator says otherwise, and a removed row states the consequence
 * where the decision was made rather than three steps later in the plan.
 */
export function EntityRow({
  fact,
  removed,
  subjectNoun,
  onRemove,
}: {
  readonly fact: EntityFact;
  readonly removed: boolean;
  readonly subjectNoun: string;
  readonly onRemove: (removed: boolean) => void;
}): ReactElement {
  return (
    <div
      className={cn(
        "group flex items-center gap-3 rounded-md border px-4 py-3",
        "",
        removed ? "border-amber/40 bg-amber/10" : "border-line bg-card hover:bg-raised"
      )}
    >
      <div className={cn("min-w-0 flex-1", removed ? "opacity-70" : "")}>
        <div
          className={cn(
            "truncate text-sm font-medium text-fg",
            removed ? "line-through decoration-1" : ""
          )}
        >
          {fact.name}
        </div>
        <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-muted">
          <Mono className="shrink-0">{fact.key}</Mono>
          {fact.detail === null ? null : (
            <>
              <span aria-hidden className="text-muted">
                ·
              </span>
              <Mono className="truncate text-muted" title={fact.detailTitle ?? fact.detail}>
                {fact.detail}
              </Mono>
            </>
          )}
        </div>
      </div>

      {removed ? (
        <>
          <Chip tone="amber">Retires on apply</Chip>
          <Button
            size="sm"
            variant="quiet"
            onClick={(): void => {
              onRemove(false);
            }}
          >
            <Undo2 /> Undo
          </Button>
        </>
      ) : (
        <>
          {fact.subjects.length === 0 ? null : (
            <Chip tone="neutral" title={fact.subjects.join(" · ")}>
              {fact.subjects.length} {subjectNoun}
            </Chip>
          )}
          <Button
            size="sm"
            variant="quiet"
            /* Always drawn, never hover-only: a control an operator has to
               discover by sweeping the mouse is a control that is not there.
               Quiet, not outlined — a border on every row is a border that has
               not justified itself. */
            aria-label={`Remove ${fact.name}`}
            onClick={(): void => {
              onRemove(true);
            }}
          >
            <Minus /> Remove
          </Button>
        </>
      )}
    </div>
  );
}
