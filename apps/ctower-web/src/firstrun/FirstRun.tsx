import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
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

  const go = (next: number): void => {
    setOutcome(null);
    setStep(next);
  };

  const start = (): void => {
    setOutcome({ kind: "asking" });
    void (async (): Promise<void> => {
      const answer = await createCompany(bundleOf(answers), previewing);
      setOutcome(answer);
      if (answer.kind === "answered" && !previewing) {
        onCreated();
      }
    })();
  };

  const shared = { answers, onAnswers: setAnswers };

  switch (step) {
    case 1:
      return (
        <NameStep
          {...shared}
          onNext={(): void => {
            go(2);
          }}
        />
      );
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
  previewing: boolean
): Promise<Answer<unknown>> {
  const checked = await ask(() => computations.validateCompanyBundle({ body: { bundle } }));
  if (checked.kind !== "answered") {
    return checked;
  }
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
