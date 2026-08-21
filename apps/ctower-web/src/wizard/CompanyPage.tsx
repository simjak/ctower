import { ArrowLeft, ArrowRight } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { Button } from "../ui/primitives";
import { ApplyStep } from "./apply/ApplyStep";
import { CheckStep } from "./check/CheckStep";
import { ComposeStep } from "./compose/ComposeStep";
import { Frame } from "./Frame";
import { modeTitle } from "./mode";
import { ReviewStep } from "./review/ReviewStep";
import { movedCount } from "./review/actions";
import type { Seed } from "./useSeed";
import { useWizard } from "./useWizard";

/**
 * The Company page: the full bundle editor, four steps, inside the shell.
 *
 * Every forward control is disabled until the step behind it has an answer that
 * permits it: a bundle that did not check does not plan, a plan that moves
 * nothing does not apply, and apply does not arm until the operator says on
 * screen that it is theirs.
 */
export function CompanyPage({ seed }: { readonly seed: Seed }): ReactElement {
  const wizard = useWizard(seed);
  const plan = wizard.plan.kind === "answered" ? wizard.plan.value : null;

  return (
    <Frame current={wizard.step} reached={wizard.reached} footer={footerFor(wizard, plan)}>
      {wizard.step === "company" ? (
        <ComposeStep
          seed={seed}
          draft={wizard.draft}
          onDraft={wizard.setDraft}
          title={modeTitle({ kind: "answered", value: seed })}
        />
      ) : null}
      {wizard.step === "check" ? <CheckStep answer={wizard.check} /> : null}
      {wizard.step === "review" ? <ReviewStep answer={wizard.plan} /> : null}
      {wizard.step === "apply" && plan !== null ? (
        <ApplyStep
          plan={plan}
          answer={wizard.applied}
          armed={wizard.armed}
          onArm={wizard.setArmed}
        />
      ) : null}
    </Frame>
  );
}

function footerFor(wizard: ReturnType<typeof useWizard>, plan: Plan): ReactNode {
  switch (wizard.step) {
    case "company":
      return (
        <>
          <span className="flex-1" />
          <Button variant="primary" onClick={wizard.runCheck}>
            Check the bundle <ArrowRight />
          </Button>
        </>
      );
    case "check":
      return (
        <>
          <Back
            onBack={(): void => {
              wizard.go("company");
            }}
          />
          <span className="flex-1" />
          <Button
            variant="primary"
            onClick={wizard.runPlan}
            disabled={!(wizard.check.kind === "answered" && wizard.check.value.valid)}
            title={
              wizard.check.kind === "answered" && wizard.check.value.valid
                ? undefined
                : "The bundle has to check out first."
            }
          >
            Review changes <ArrowRight />
          </Button>
        </>
      );
    case "review":
      return (
        <>
          <Back
            onBack={(): void => {
              wizard.go("check");
            }}
          />
          <span className="flex-1" />
          <Button
            variant="primary"
            onClick={(): void => {
              wizard.go("apply");
            }}
            disabled={plan === null || movedCount(plan.actions) === 0}
            title={
              plan !== null && movedCount(plan.actions) === 0
                ? "There is nothing to apply."
                : undefined
            }
          >
            Apply <ArrowRight />
          </Button>
        </>
      );
    case "apply":
      return wizard.applied === null ? (
        <>
          <Back
            onBack={(): void => {
              wizard.go("review");
            }}
          />
          <span className="flex-1" />
          <Button
            variant="primary"
            disabled={!wizard.armed || plan === null}
            onClick={(): void => {
              if (plan !== null) {
                wizard.runApply(plan);
              }
            }}
            title={wizard.armed ? undefined : "Confirm the authority above first."}
          >
            Apply as operator
          </Button>
        </>
      ) : (
        <>
          <Back
            onBack={(): void => {
              wizard.go("review");
            }}
          />
          <span className="flex-1" />
        </>
      );
  }
}

type Plan = Parameters<ReturnType<typeof useWizard>["runApply"]>[0] | null;

function Back({ onBack }: { readonly onBack: () => void }): ReactElement {
  return (
    <Button variant="ghost" onClick={onBack}>
      <ArrowLeft /> Back
    </Button>
  );
}
