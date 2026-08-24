import { Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Chip } from "../../ui/primitives";
import type { EntityFact } from "../read";
import { RepositoryLink } from "./RepositoryLink";

/**
 * One project or one agent.
 *
 * A row says the name a person gave the thing, and one supporting fact: for an
 * agent, what the harness it runs on is called; for a project, where its code
 * is, as a link. It does not say the key it is addressed by, the revision
 * pinning it, the reference behind either of those names, or the principals a
 * binding lists. Those are the record's own vocabulary: they are what this
 * console reads to find the row, never what the operator reads once it is
 * drawn. The count of bindings is a fact about the operator's world; the
 * identifiers inside it are not, so the chip counts and does not list.
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
        {/* The name, and the one supporting fact a person reads. For an agent
            that is what its harness is called; for a project it is the
            repository, which is also somewhere to go, so it draws as a link
            rather than as a sentence about one. A row never carries both. */}
        {fact.repository === null ? null : <RepositoryLink repository={fact.repository} />}
        {fact.detail === null ? null : (
          <div className="mt-0.5 min-w-0 truncate text-xs text-muted">{fact.detail}</div>
        )}
      </div>

      {fact.subjects.length === 0 ? null : (
        <Chip>
          {fact.subjects.length} {fact.subjects.length === 1 ? subjectNoun : `${subjectNoun}s`}
        </Chip>
      )}
      <Button size="sm" variant="quiet" className="px-2" disabled aria-label={why} title={why}>
        <Trash2 />
      </Button>
    </div>
  );
}
