import { useCallback, useState } from "react";
import type {
  CompanyBundleCommandResult,
  CompanyBundlePlan,
  CompanyBundleValidationResult,
} from "@ctower/client";
import { ask, commands, computations } from "../api/client";
import type { Answer } from "../api/client";
import { commandKeyFor } from "./apply/commandKey";
import { documentOf, draftFrom, EMPTY_TEMPLATE } from "./bundle";
import type { Draft } from "./bundle";
import type { StepKey } from "./steps";
import type { Seed } from "./useSeed";

export interface Wizard {
  readonly draft: Draft;
  readonly setDraft: (draft: Draft) => void;
  readonly step: StepKey;
  readonly reached: StepKey;
  /** Move to a step that has already been reached; it runs nothing. */
  readonly go: (step: StepKey) => void;
  readonly check: Answer<CompanyBundleValidationResult>;
  readonly runCheck: () => void;
  readonly plan: Answer<CompanyBundlePlan>;
  readonly runPlan: () => void;
  readonly armed: boolean;
  readonly setArmed: (armed: boolean) => void;
  readonly applied: Answer<CompanyBundleCommandResult> | null;
  readonly runApply: (plan: CompanyBundlePlan) => void;
}

const ASKING = { kind: "asking" } as const;

/**
 * One draft, one answer per step, and the rule that ties them: a step's answer
 * is thrown away the moment the draft it was about changes. A plan computed for
 * a company that has since been edited is not this company's plan, and carrying
 * it forward is how a wizard applies something the operator did not review.
 */
export function useWizard(seed: Seed): Wizard {
  const [draft, setDraftState] = useState<Draft>(() =>
    draftFrom(seed.kind === "exported" ? seed.result.bundle : EMPTY_TEMPLATE)
  );
  const [step, setStep] = useState<StepKey>("company");
  const [reached, setReached] = useState<StepKey>("company");
  const [check, setCheck] = useState<Answer<CompanyBundleValidationResult>>(ASKING);
  const [plan, setPlan] = useState<Answer<CompanyBundlePlan>>(ASKING);
  const [armed, setArmed] = useState(false);
  const [applied, setApplied] = useState<Answer<CompanyBundleCommandResult> | null>(null);

  const setDraft = useCallback((next: Draft): void => {
    setDraftState(next);
    setCheck(ASKING);
    setPlan(ASKING);
    setArmed(false);
    setApplied(null);
    setReached("company");
  }, []);

  const runCheck = useCallback((): void => {
    setStep("check");
    setReached("check");
    setCheck(ASKING);
    void (async (): Promise<void> => {
      setCheck(
        await ask(() => computations.validateCompanyBundle({ body: { bundle: documentOf(draft) } }))
      );
    })();
  }, [draft]);

  const runPlan = useCallback((): void => {
    setStep("review");
    setReached("review");
    setPlan(ASKING);
    void (async (): Promise<void> => {
      setPlan(
        await ask(() => computations.planCompanyBundle({ body: { bundle: documentOf(draft) } }))
      );
    })();
  }, [draft]);

  const runApply = useCallback(
    (accepted: CompanyBundlePlan): void => {
      setApplied(ASKING);
      void (async (): Promise<void> => {
        setApplied(
          await ask(() =>
            commands.applyCompanyBundle({
              IdempotencyKey: commandKeyFor(accepted.plan_digest),
              body: {
                bundle: documentOf(draft),
                expected_active_version: accepted.base_version,
                plan_digest: accepted.plan_digest,
              },
            })
          )
        );
      })();
    },
    [draft]
  );

  const go = useCallback((target: StepKey): void => {
    setStep(target);
  }, []);

  return {
    draft,
    setDraft,
    step,
    reached,
    go,
    check,
    runCheck,
    plan,
    runPlan,
    armed,
    setArmed,
    applied,
    runApply,
  };
}
