import { Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Chip, Mono } from "../../ui/primitives";
import type { EntityFact } from "../read";

/**
 * One project or one agent.
 *
 * The bin is drawn and it does not work, which is the honest state and not an
 * oversight. Increment 1's registry refuses any plan carrying a deprecation —
 * `bundle-compatibility-refused`, at apply, after the whole review — so a
 * working bin could only ever build a document that nothing will accept. It
 * renders quiet, disabled, and says why on hover and to a screen reader, the
 * same way every other unbuilt thing on this surface does.
 */
export function EntityRow({
  fact,
  subjectNoun,
}: {
  readonly fact: EntityFact;
  /** Singular; the row pluralises it against the count. */
  readonly subjectNoun: string;
}): ReactElement {
  const why = `Taking ${fact.name} out is not supported yet — ctower refuses to apply a removal.`;
  return (
    <div className="flex items-center gap-3 rounded-md border border-line bg-card px-4 py-3 hover:bg-raised">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-fg">{fact.name}</div>
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

      {fact.subjects.length === 0 ? null : (
        <Chip title={fact.subjects.join(" · ")}>
          {fact.subjects.length} {fact.subjects.length === 1 ? subjectNoun : `${subjectNoun}s`}
        </Chip>
      )}
      <Button size="sm" variant="quiet" className="px-2" disabled aria-label={why} title={why}>
        <Trash2 />
      </Button>
    </div>
  );
}
