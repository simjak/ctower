import type { ReactElement } from "react";
import { Badge, Mono } from "../../ui/primitives";
import { Checkbox } from "../../ui/form";
import { cn } from "../../ui/cn";
import type { EntityFact } from "../read";

/**
 * One project or one agent, as a row the operator can read at a glance and take
 * out of the company with one click.
 *
 * Hierarchy is structure, not decoration: the name carries the weight, the key
 * and its supporting fact sit under it in the machine face, and the only colour
 * on the row is the checkbox when it is on.
 */
export function EntityRow({
  fact,
  kept,
  subjectNoun,
  onKeep,
}: {
  readonly fact: EntityFact;
  readonly kept: boolean;
  readonly subjectNoun: string;
  readonly onKeep: (kept: boolean) => void;
}): ReactElement {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border px-4 py-3",
        "transition-colors duration-(--motion-duration-fast)",
        kept ? "border-line-2 bg-surface-2 hover:bg-raised/50" : "border-line bg-transparent"
      )}
    >
      <Checkbox checked={kept} onCheckedChange={onKeep} label={`Include ${fact.name}`} />
      <div className={cn("min-w-0 flex-1", kept ? "" : "opacity-50")}>
        <div className="truncate text-sm font-medium text-ink">{fact.name}</div>
        <div className="mt-0.5 flex min-w-0 items-center gap-1.5 text-ink-3">
          <Mono className="shrink-0">{fact.key}</Mono>
          {fact.detail === null ? null : (
            <>
              <span aria-hidden className="text-ink-4">
                ·
              </span>
              <Mono className="truncate text-ink-4" title={fact.detailTitle ?? fact.detail}>
                {fact.detail}
              </Mono>
            </>
          )}
        </div>
      </div>
      {fact.subjects.length === 0 ? null : (
        <Badge tone="neutral" title={fact.subjects.join(" · ")}>
          {fact.subjects.length} {subjectNoun}
        </Badge>
      )}
    </div>
  );
}
