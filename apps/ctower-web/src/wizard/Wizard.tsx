import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import type { CompanyBundleValidationResult } from "@ctower/client";
import { ask, computations } from "../api/client";
import type { Answer } from "../api/client";
import { Button, PageHead } from "../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "./states";
import { CheckStep } from "./check/CheckStep";
import { ComposeStep } from "./compose/ComposeStep";
import { StepRail } from "./StepRail";
import { documentOf, draftFrom, EMPTY_TEMPLATE } from "./bundle";
import type { Draft } from "./bundle";
import { STEPS } from "./steps";
import type { StepKey } from "./steps";
import { useSeed } from "./useSeed";
import type { Seed } from "./useSeed";

/**
 * The wizard, and the only screen this application has. It holds one draft and
 * one answer per step, so a step never renders a fact an earlier step merely
 * believed.
 */
export function Wizard(): ReactElement {
  const seed = useSeed();

  if (seed.kind === "answered") {
    return <Steps seed={seed.value} />;
  }

  return (
    <Frame current="company" reached="company">
      <PageHead title="Company details" subtitle="" />
      {seed.kind === "asking" ? <Asking what="Reading this company" /> : null}
      {seed.kind === "refused" ? (
        <Refused problem={seed.problem} action="Nothing was composed. Reload to ask again." />
      ) : null}
      {seed.kind === "unreachable" ? (
        <Unreachable
          detail={seed.detail}
          action="This is not an empty company; it is a company that was not read. Reload to ask again."
        />
      ) : null}
      {seed.kind === "malformed" ? <Malformed detail={seed.detail} /> : null}
    </Frame>
  );
}

function Steps({ seed }: { readonly seed: Seed }): ReactElement {
  const [draft, setDraft] = useState<Draft>(() =>
    draftFrom(seed.kind === "exported" ? seed.result.bundle : EMPTY_TEMPLATE)
  );
  const [step, setStep] = useState<StepKey>("company");
  const [reached, setReached] = useState<StepKey>("company");
  const [check, setCheck] = useState<Answer<CompanyBundleValidationResult>>({ kind: "asking" });

  const runCheck = useCallback((): void => {
    setStep("check");
    setReached("check");
    setCheck({ kind: "asking" });
    const call = async (): Promise<void> => {
      setCheck(
        await ask(() => computations.validateCompanyBundle({ body: { bundle: documentOf(draft) } }))
      );
    };
    void call();
  }, [draft]);

  return (
    <Frame current={step} reached={reached}>
      {step === "company" ? <ComposeStep seed={seed} draft={draft} onDraft={setDraft} /> : null}
      {step === "check" ? <CheckStep answer={check} /> : null}
      <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
        {step === "company" ? null : (
          <Button
            variant="ghost"
            onClick={(): void => {
              setStep("company");
            }}
          >
            <ArrowLeft /> Back
          </Button>
        )}
        <span className="flex-1" />
        {step === "company" ? (
          <Button variant="cta" onClick={runCheck}>
            Check the bundle <ArrowRight />
          </Button>
        ) : null}
        {step === "check" ? (
          <Button variant="cta" onClick={runCheck} disabled={check.kind === "asking"}>
            Check again
          </Button>
        ) : null}
      </footer>
    </Frame>
  );
}

function Frame({
  current,
  reached,
  children,
}: {
  readonly current: StepKey;
  readonly reached: StepKey;
  readonly children: ReactElement | readonly (ReactElement | null)[];
}): ReactElement {
  return (
    <div className="mx-auto grid max-w-[1000px] gap-8 px-6 py-8 md:grid-cols-[180px_minmax(0,1fr)]">
      <StepRail steps={STEPS} current={current} reached={reached} />
      <div className="min-w-0" aria-live="polite">
        {children}
      </div>
    </div>
  );
}
