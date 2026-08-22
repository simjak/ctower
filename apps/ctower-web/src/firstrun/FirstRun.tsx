import { useRef, useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { ask, commands, computations } from "../api/client";
import type { Answer } from "../api/client";
import { commandKeyFor } from "../api/commandKey";
import { BLANK, bundleOf } from "./answers";
import type { Answers } from "./answers";
import type { FirstRunOutcome } from "./outcome";
import { ReviewStep } from "./ReviewStep";
import { AgentStep, HarnessStep, MissionStep, NameStep } from "./steps";

/**
 * First run: five steps, one question each, and one command at the end.
 *
 * Two rules govern every asynchronous act here, and both exist because the
 * screen can change while the network is thinking.
 *
 * **Generation.** Every navigation and every answer edit bumps a generation.
 * A response whose generation is stale is discarded — it can neither advance a
 * step nor authorize a command. Without it, a slow key check could wave through
 * a key the operator edited after pressing Next, and a Back during apply could
 * leave an obsolete bundle applying behind the screen.
 *
 * **Fail closed.** Advancing requires a positive answer. Silence, a contract
 * fault, or any refusal keeps the operator where they are with the reason on
 * screen; nothing is treated as permission by default.
 */
export function FirstRun({
  onCreated,
  previewing,
}: {
  readonly onCreated: () => void;
  readonly previewing: boolean;
}): ReactElement {
  const [step, setStep] = useState(1);
  const [answers, setAnswersState] = useState<Answers>(BLANK);
  const [applied, setApplied] = useState<FirstRunOutcome | null>(null);
  const [keyCheck, setKeyCheck] = useState<Answer<unknown> | null>(null);
  const generation = useRef(0);

  /** Everything in flight becomes stale the moment anything changes. */
  const supersede = (): number => {
    generation.current += 1;
    return generation.current;
  };

  const setAnswers = (next: Answers): void => {
    supersede();
    setKeyCheck(null);
    setApplied(null);
    setAnswersState(next);
  };

  const go = (next: number): void => {
    supersede();
    setKeyCheck(null);
    setApplied(null);
    setStep(next);
  };

  const busy = keyCheck?.kind === "asking" || applied?.kind === "asking";

  /**
   * The key is checked against the live registry before the operator can walk
   * four more screens on it — and the check is bound to the draft it was made
   * for, so an edit made while it was in flight cannot ride the old answer.
   */
  const leaveName = (): void => {
    const mine = supersede();
    setKeyCheck({ kind: "asking" });
    void (async (): Promise<void> => {
      const answer = await ask(() =>
        computations.validateCompanyBundle({ body: { bundle: bundleOf(answers) } })
      );
      if (generation.current !== mine) {
        return;
      }
      if (answer.kind === "answered") {
        setKeyCheck(null);
        setStep(2);
        return;
      }
      setKeyCheck(answer);
    })();
  };

  const start = (): void => {
    const mine = supersede();
    const bundle = bundleOf(answers);
    setApplied({ kind: "asking" });
    void (async (): Promise<void> => {
      const answer = await createCompany(bundle, previewing);
      if (generation.current !== mine) {
        return;
      }
      setApplied(answer);
      // Only an accepted command created a company. `durability_pending` is the
      // same shape and the same status family, and promoting it would tell the
      // operator a thing exists that the record has not agreed to yet.
      if (
        !previewing &&
        answer.kind === "answered" &&
        answer.value.durability_state === "accepted"
      ) {
        onCreated();
      }
    })();
  };

  const shared = { answers, onAnswers: setAnswers, busy };

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
            supersede();
            setAnswersState({ ...answers, mission: "", criterion: "" });
            setStep(5);
          }}
        />
      );
    default:
      return (
        <ReviewStep
          answers={answers}
          applied={applied}
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
 * A forced preview stops after the plan: the preview exists so this screen can
 * be looked at on a tower that already has a company, and there the command
 * would replace that company's whole definition.
 */
async function createCompany(
  bundle: CompanyBundleDocument,
  previewing: boolean
): Promise<FirstRunOutcome> {
  const checked = await ask(() => computations.validateCompanyBundle({ body: { bundle } }));
  if (checked.kind !== "answered") {
    return checked;
  }
  const planned = await ask(() => computations.planCompanyBundle({ body: { bundle } }));
  if (planned.kind !== "answered") {
    return planned;
  }
  if (previewing) {
    return { kind: "previewed" };
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
