import type { ReactElement } from "react";
import { Hint } from "../ui/form";
import { Mono } from "../ui/primitives";
import { Instant } from "./facts";
import type { StandingWorkflow } from "./workflow";

/**
 * Where this ticket has been, and where it stands.
 *
 * The mockup draws the stages ahead as well. No operation the authored
 * contract declares returns a workflow's definition, so the stages ahead are
 * not known here, and drawing empty cells for them would be a plan this
 * console invented. The ladder is the record's own walk: one cell per stage
 * the ticket actually entered, in the order it entered them.
 *
 * No cell carries a mark. `●` means proven and `⟳` means working, and neither
 * is what "the ticket left this stage" says — the position is the fact, and a
 * borrowed glyph would claim a second one.
 */
export function StageLadder({ standing }: { readonly standing: StandingWorkflow }): ReactElement {
  return (
    <section aria-label="Stages">
      <div className="mb-2 flex items-center gap-1.5">
        <span className="text-2xs text-muted">STAGES</span>
        <Hint text="The stages this ticket has entered. ctower declares no read for the stages ahead of it." />
        <span className="flex-1" />
        <Mono className="text-muted" title={standing.reference}>
          {standing.reference}
        </Mono>
      </div>
      <ol className="m-0 flex list-none flex-wrap gap-1.5 p-0">
        {standing.walked.map((entry, index) => (
          <li key={entry.stage} className="min-w-0">
            <Cell
              stage={entry.stage}
              enteredAt={entry.enteredAt}
              here={index === standing.walked.length - 1}
              closed={standing.closed}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}

function Cell({
  stage,
  enteredAt,
  here,
  closed,
}: {
  readonly stage: string;
  readonly enteredAt: string;
  readonly here: boolean;
  readonly closed: boolean;
}): ReactElement {
  // Amber is where work stands, and a closed workflow is not work standing
  // anywhere. The last cell of a closed ladder still says it is the last cell,
  // in a neutral it earns, so "here and live" and "here and finished" are not
  // drawn as the same fact.
  const edge = !here
    ? "border-line"
    : closed
      ? "border-fg/35 bg-raised"
      : "border-amber bg-amber/10";
  return (
    <div className={`rounded-sm border px-3 py-1.5 ${edge}`}>
      <Mono className={here ? "text-fg" : "text-muted"}>{stage}</Mono>
      <div className="mt-0.5 flex items-baseline gap-2">
        {here ? (
          <span className={closed ? "text-2xs text-muted" : "text-2xs text-amber-ink"}>
            {closed ? "closed here" : "here"}
          </span>
        ) : null}
        <Instant at={enteredAt} />
      </div>
    </div>
  );
}
