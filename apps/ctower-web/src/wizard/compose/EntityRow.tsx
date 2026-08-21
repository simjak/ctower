import { Trash2, Undo2 } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Chip, Mono } from "../../ui/primitives";
import { cn } from "../../ui/cn";
import type { EntityFact } from "../read";

/**
 * One project or one agent.
 *
 * The control is a bin, drawn always rather than on hover, and it says what it
 * is to a screen reader. What removing means is named where the operator
 * commits to it — in the review and on the authority gate — rather than sitting
 * on the row as standing text: a row that permanently explains itself is the
 * rationale habit wearing a border.
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
        "flex items-center gap-3 rounded-md border px-4 py-3",
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
        <Button
          size="sm"
          variant="quiet"
          aria-label={`Keep ${fact.name}`}
          onClick={(): void => {
            onRemove(false);
          }}
        >
          <Undo2 /> Undo
        </Button>
      ) : (
        <>
          {fact.subjects.length === 0 ? null : (
            <Chip title={fact.subjects.join(" · ")}>
              {fact.subjects.length} {subjectNoun}
            </Chip>
          )}
          <Button
            size="sm"
            variant="quiet"
            className="px-2 hover:text-danger"
            aria-label={`Remove ${fact.name}`}
            title={`Remove ${fact.name}`}
            onClick={(): void => {
              onRemove(true);
            }}
          >
            <Trash2 />
          </Button>
        </>
      )}
    </div>
  );
}
