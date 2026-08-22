import { ArrowLeft } from "lucide-react";
import type { ReactElement } from "react";
import type { CompanyBundleCommandResult } from "@ctower/client";
import type { Answer } from "../../api/client";
import { Button, Chip, Mono, PageHead } from "../../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../states";
import { shortDigest } from "../bundle";
import { AuthorityGate } from "./AuthorityGate";
import { PlanDiff } from "./PlanDiff";
import { Receipt } from "./Receipt";
import { movedCount } from "./actions";
import type { Standing } from "../standing";

/**
 * Review and apply, as one thing.
 *
 * They were two steps and that was two screens too many: an operator reading a
 * diff is deciding whether to apply it, and making them press *next* to reach
 * the decision they already made is ceremony. The diff, the authority it runs
 * under, and the command are one flow, and none of it exists unless the
 * definition was edited.
 */
export function ReviewPanel({
  review,
  applied,
  armed,
  onArm,
  onApply,
  onRetry,
  onBack,
  backLabel,
}: {
  readonly review: Answer<Standing>;
  readonly applied: Answer<CompanyBundleCommandResult> | null;
  readonly armed: boolean;
  readonly onArm: (armed: boolean) => void;
  readonly onApply: (standing: Standing) => void;
  /** Absent when there is nothing to send again; the receipt then offers none. */
  readonly onRetry: (() => void) | null;
  readonly onBack: () => void;
  /** Where "back" goes, named by the screen this ceremony was entered from. */
  readonly backLabel: string;
}): ReactElement {
  if (applied !== null) {
    return <Receipt applied={applied} onRetry={onRetry} onBack={onBack} backLabel={backLabel} />;
  }

  return (
    <>
      <PageHead title="Review changes" subtitle={<Summary review={review} />} />
      <Body review={review} armed={armed} onArm={onArm} />
      <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
        <Button variant="quiet" onClick={onBack}>
          <ArrowLeft /> {backLabel}
        </Button>
        <span className="flex-1" />
        {review.kind === "answered" && movedCount(review.value.plan.actions) > 0 ? (
          <Button
            variant="primary"
            disabled={!armed}
            title={armed ? undefined : "Confirm the authority above first."}
            onClick={(): void => {
              onApply(review.value);
            }}
          >
            Apply as operator
          </Button>
        ) : null}
      </footer>
    </>
  );
}

function Body({
  review,
  armed,
  onArm,
}: {
  readonly review: Answer<Standing>;
  readonly armed: boolean;
  readonly onArm: (armed: boolean) => void;
}): ReactElement {
  switch (review.kind) {
    case "asking":
      return <Asking what="Working out what would change" />;
    case "refused":
      return (
        <Refused
          problem={review.problem}
          action="Nothing was planned. Go back and change the definition."
        />
      );
    case "unreachable":
      return (
        <Unreachable
          detail={review.detail}
          action="No plan was made. This is not an empty change set."
        />
      );
    case "malformed":
      return <Malformed detail={review.detail} />;
    case "answered":
      return <Planned standing={review.value} armed={armed} onArm={onArm} />;
  }
}

function Planned({
  standing,
  armed,
  onArm,
}: {
  readonly standing: Standing;
  readonly armed: boolean;
  readonly onArm: (armed: boolean) => void;
}): ReactElement {
  const moved = movedCount(standing.plan.actions);
  return (
    <div className="space-y-4">
      {standing.validation.valid ? null : (
        <Chip tone="danger">the edited definition does not check out</Chip>
      )}
      <PlanDiff plan={standing.plan} />
      {moved === 0 ? null : <AuthorityGate plan={standing.plan} armed={armed} onArm={onArm} />}
    </div>
  );
}

/**
 * The head's own line, and it may only say what has happened.
 *
 * A refusal is not a question still out. This said "Asking the registry" above
 * a rendered refusal, which reads as a screen that has not heard back from a
 * registry that has already answered — so the line exists while the call is
 * out, and after that the body carries the fact.
 */
function Summary({ review }: { readonly review: Answer<Standing> }): ReactElement | null {
  if (review.kind === "asking") {
    return <span>Asking the registry</span>;
  }
  if (review.kind !== "answered") {
    return null;
  }
  const plan = review.value.plan;
  const moved = movedCount(plan.actions);
  return (
    <>
      {moved === 0 ? (
        <Chip>no changes</Chip>
      ) : (
        <Chip tone="amber">
          {moved} of {plan.actions.length} move
        </Chip>
      )}
      <span>
        version <Mono>{plan.base_version}</Mono> → <Mono>{plan.base_version + 1}</Mono>
      </span>
      <Mono className="text-muted" title={plan.plan_digest}>
        {shortDigest(plan.plan_digest)}
      </Mono>
    </>
  );
}
