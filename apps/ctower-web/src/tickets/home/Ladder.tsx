import type { ReactElement, ReactNode } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { cn } from "../../ui/cn";
import { order } from "../../workflows/graph";
import { splitReference, workflowFacts } from "../../workflows/read";
import { clockWords, stageWord } from "../words";
import type { StandingWorkflow } from "../workflow";
import { Absent, Section } from "./parts";

/**
 * How far the ticket has got, including the stages ahead of it.
 *
 * The shipped ladder drew only where a ticket had been, on the reasoning that
 * no operation returns a workflow's definition. That was wrong about this
 * record and the frozen spec supersedes it: a workflow is a **component of the
 * company document**, which `exportCompanyBundle` already answers with and
 * `workflows/read.ts` already reads. So the whole ladder is knowable — the
 * declared stages in the order the declared transitions run them — and the
 * walk from `getTicketTimeline` says which of them this ticket has stood at.
 *
 * When this company records no such workflow, the ladder is still drawn from
 * the walk alone and says so. A ticket running a workflow the bundle does not
 * carry is a real state, and drawing nothing would lose the walk as well.
 */
export function Ladder({
  standing,
  document,
  children,
}: {
  readonly standing: StandingWorkflow;
  /** The company record the workflow's own definition is a component of. */
  readonly document: CompanyBundleDocument;
  /** What moves it on, drawn under the ladder it moves along. */
  readonly children: ReactNode;
}): ReactElement {
  const stages = stagesOf(standing, document);
  const walked = new Set(standing.walked.map((entry) => entry.stage));
  const entered = standing.walked.find((entry) => entry.stage === standing.stage) ?? null;

  return (
    <Section
      title="How far it has got"
      note={
        entered === null ? null : (
          <>
            In {stageWord(standing.stage)} since {clockWords(entered.enteredAt)}
          </>
        )
      }
    >
      <ol className="m-0 flex list-none gap-0 p-0">
        {stages.map((stage) => (
          <Step
            key={stage}
            word={stageWord(stage)}
            here={stage === standing.stage}
            behind={walked.has(stage) && stage !== standing.stage}
            closed={standing.closed}
          />
        ))}
      </ol>
      {stages.length === standing.walked.length ? (
        <Absent>
          This company records no definition for the workflow this ticket runs, so the steps ahead
          of it are not known here. What is drawn is where it has actually been.
        </Absent>
      ) : null}
      {children}
    </Section>
  );
}

/**
 * The stages this ladder draws.
 *
 * The definition's own order when the company records one, and the walk when it
 * does not. A stage the ticket entered that the definition never declares is
 * kept: the record says it happened, and a ladder that dropped it would be the
 * definition overruling the event that actually occurred.
 */
function stagesOf(standing: StandingWorkflow, document: CompanyBundleDocument): readonly string[] {
  const [key] = splitReference(standing.reference);
  const workflow = workflowFacts(document).find((fact) => fact.key === key);
  if (workflow === undefined) {
    return standing.walked.map((entry) => entry.stage);
  }
  const declared = order(workflow).path.map((stage) => stage.key);
  const extra = standing.walked
    .map((entry) => entry.stage)
    .filter((stage) => !declared.includes(stage));
  return [...declared, ...extra];
}

/**
 * One step. Amber is where work stands, and a closed workflow is not work
 * standing anywhere — so the last step of a finished ladder is marked as the
 * end rather than as a place something is happening.
 */
function Step({
  word,
  here,
  behind,
  closed,
}: {
  readonly word: string;
  readonly here: boolean;
  readonly behind: boolean;
  readonly closed: boolean;
}): ReactElement {
  return (
    <li className="relative min-w-0 flex-1 pt-3.5 text-center">
      <span
        aria-hidden
        className={cn(
          "absolute top-1.5 left-0 h-0.5 w-full",
          behind || here ? "bg-amber/45" : "bg-line"
        )}
      />
      <span
        aria-hidden
        className={cn(
          "absolute top-0 left-1/2 size-3 -translate-x-1/2 rounded-full border-2",
          behind && "border-transparent bg-amber/45",
          here && !closed && "border-transparent bg-amber",
          here && closed && "border-transparent bg-fg/45",
          !here && !behind && "border-line bg-bg"
        )}
      />
      <span
        className={cn(
          "block truncate px-0.5 text-2xs",
          here ? "font-semibold text-fg" : behind ? "text-muted" : "text-muted/70"
        )}
      >
        {word}
      </span>
      {here ? <span className="sr-only">— where it stands now</span> : null}
    </li>
  );
}
