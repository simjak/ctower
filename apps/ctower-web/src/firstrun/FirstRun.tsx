import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument, CompanyBundleValidationResult } from "@ctower/client";
import { ask, commands, computations } from "../api/client";
import type { Answer } from "../api/client";
import { commandKeyFor } from "../wizard/apply/commandKey";
import { BLANK, bundleOf } from "./answers";
import type { Answers } from "./answers";
import { ReviewStep } from "./ReviewStep";
import { AgentStep, HarnessStep, MissionStep, NameStep } from "./steps";

/**
 * First run: five steps, one question each, and one command at the end.
 *
 * The order follows the runtime rather than the org chart — the harness is
 * chosen before the staff, because the agent is created *on* it. Each step
 * collects an answer and nothing more; the bundle is assembled once, at the
 * end, and checked, planned and applied as one act.
 */
export function FirstRun({
  onCreated,
  previewing,
}: {
  readonly onCreated: () => void;
  readonly previewing: boolean;
}): ReactElement {
  const [step, setStep] = useState(1);
  const [answers, setAnswers] = useState<Answers>(BLANK);
  const [outcome, setOutcome] = useState<Answer<unknown> | null>(null);
  const [validation, setValidation] = useState<CompanyBundleValidationResult | null>(null);
  const [keyCheck, setKeyCheck] = useState<Answer<unknown> | null>(null);

  const go = (next: number): void => {
    setOutcome(null);
    setValidation(null);
    setStep(next);
  };

  /**
   * The key is checked here, against the live registry, before the operator can
   * walk four more screens on it.
   *
   * A company key must equal the authenticated tenant's, and nothing on the
   * authored read surface returns that key on a tower with no company — so it
   * cannot be pre-filled, and a wrong one used to survive all the way to Review
   * before the registry refused it. Asking now turns a dead end at the end into
   * a correction on the field that caused it.
   *
   * Only `bundle-grant-refused` holds the operator here. Every other answer is
   * about the rest of the bundle, which the later steps are still filling in,
   * and Review is where those belong.
   */
  const leaveName = (): void => {
    setKeyCheck({ kind: "asking" });
    void (async (): Promise<void> => {
      const answer = await ask(() =>
        computations.validateCompanyBundle({ body: { bundle: bundleOf(answers) } })
      );
      if (answer.kind === "refused" && answer.problem.code === "bundle-grant-refused") {
        setKeyCheck(answer);
        return;
      }
      setKeyCheck(null);
      go(2);
    })();
  };

  const start = (): void => {
    setOutcome({ kind: "asking" });
    void (async (): Promise<void> => {
      const answer = await createCompany(bundleOf(answers), previewing, setValidation);
      setOutcome(answer);
      if (answer.kind === "answered" && !previewing) {
        onCreated();
      }
    })();
  };

  const shared = { answers, onAnswers: setAnswers };

  switch (step) {
    case 1:
      return <NameStep {...shared} onNext={leaveName} keyCheck={keyCheck} />;
    case 2:
      return (
        <HarnessStep
          {...shared}
          onBack={(): void => {
            go(1);
          }}
          onNext={(): void => {
            go(3);
          }}
        />
      );
    case 3:
      return (
        <AgentStep
          {...shared}
          onBack={(): void => {
            go(2);
          }}
          onNext={(): void => {
            go(4);
          }}
        />
      );
    case 4:
      return (
        <MissionStep
          {...shared}
          onBack={(): void => {
            go(3);
          }}
          onNext={(): void => {
            go(5);
          }}
          onSkip={(): void => {
            setAnswers({ ...answers, mission: "", criterion: "" });
            go(5);
          }}
        />
      );
    default:
      return (
        <ReviewStep
          answers={answers}
          outcome={outcome}
          validation={validation}
          previewing={previewing}
          onStart={start}
          onBack={(): void => {
            go(4);
          }}
        />
      );
  }
}

/**
 * Check, plan, apply — one act, stopping at the first thing that is not an
 * answer. The plan's own digest and base version are what apply is sent, so the
 * command can only ever apply the plan that was actually computed.
 *
 * A forced preview stops after the plan. The preview exists so this screen can
 * be looked at on a tower that already has a company, and on such a tower the
 * command would not be a no-op — it would replace that company's whole
 * definition with the four components this wizard just minted. So the reads run
 * for real, the write does not run at all, and the screen says which.
 */
async function createCompany(
  bundle: CompanyBundleDocument,
  previewing: boolean,
  onValidation: (validation: CompanyBundleValidationResult) => void
): Promise<Answer<unknown>> {
  const checked = await ask(() => computations.validateCompanyBundle({ body: { bundle } }));
  if (checked.kind !== "answered") {
    return checked;
  }
  onValidation(checked.value);
  const planned = await ask(() => computations.planCompanyBundle({ body: { bundle } }));
  if (planned.kind !== "answered") {
    return planned;
  }
  if (previewing) {
    return { kind: "answered", value: planned.value };
  }
  return ask(() =>
    commands.applyCompanyBundle({
      IdempotencyKey: commandKeyFor(planned.value.plan_digest),
      body: {
        bundle,
        expected_active_version: planned.value.base_version,
        plan_digest: planned.value.plan_digest,
      },
    })
  );
}
