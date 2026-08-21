import { useCallback, useEffect, useState } from "react";
import type {
  CompanyBundleCommandResult,
  CompanyBundleDocument,
  CompanyBundlePlan,
  CompanyBundleValidationResult,
} from "@ctower/client";
import { ask, commands, computations } from "../api/client";
import type { Answer } from "../api/client";
import { commandKeyFor } from "./apply/commandKey";
import { documentOf, draftFrom, EMPTY_TEMPLATE, editCount } from "./bundle";
import type { Draft } from "./bundle";
import type { Seed } from "./useSeed";

/** What the registry says about one exact document. */
export interface Standing {
  readonly validation: CompanyBundleValidationResult;
  readonly plan: CompanyBundlePlan;
}

export type Mode = "definition" | "review";

export interface Company {
  readonly draft: Draft;
  readonly setDraft: (draft: Draft) => void;
  readonly edits: number;
  /** The registry's word on the definition as it stands, asked once. */
  readonly standing: Answer<Standing>;
  readonly mode: Mode;
  /** The registry's word on the edited definition; only asked when there are edits. */
  readonly review: Answer<Standing>;
  readonly openReview: () => void;
  readonly closeReview: () => void;
  readonly armed: boolean;
  readonly setArmed: (armed: boolean) => void;
  readonly applied: Answer<CompanyBundleCommandResult> | null;
  readonly apply: (plan: CompanyBundlePlan) => void;
}

const ASKING = { kind: "asking" } as const;

/**
 * One page, and a ceremony that only exists when it has something to be about.
 *
 * The definition is read and stood up once: checked and planned exactly as it
 * is, so the page can say `valid · 5 of 5 · no changes` as a fact rather than
 * walking an operator through four steps to discover that nothing happened.
 *
 * Review is not a step. It is what edits produce: no edits, no review, no apply
 * gate, no stepper. The moment the draft differs from what is recorded, the way
 * forward appears; the moment it stops differing, it goes away again.
 */
export function useCompany(seed: Seed): Company {
  const recorded = seed.kind === "exported" ? seed.result.bundle : EMPTY_TEMPLATE;
  const [draft, setDraftState] = useState<Draft>(() => draftFrom(recorded));
  const [standing, setStanding] = useState<Answer<Standing>>(ASKING);
  const [mode, setMode] = useState<Mode>("definition");
  const [review, setReview] = useState<Answer<Standing>>(ASKING);
  const [armed, setArmed] = useState(false);
  const [applied, setApplied] = useState<Answer<CompanyBundleCommandResult> | null>(null);

  useEffect(() => {
    let live = true;
    // Declared, then called: an immediately-invoked async closure lets the
    // checker narrow `live` to its initializer and the guard reads as dead.
    const stand = async (): Promise<void> => {
      const answer = await standingOf(recorded);
      if (!live) {
        return;
      }
      setStanding(answer);
    };
    void stand();
    return (): void => {
      live = false;
    };
  }, [recorded]);

  const setDraft = useCallback((next: Draft): void => {
    setDraftState(next);
    setMode("definition");
    setReview(ASKING);
    setArmed(false);
    setApplied(null);
  }, []);

  const openReview = useCallback((): void => {
    setMode("review");
    setReview(ASKING);
    void (async (): Promise<void> => {
      setReview(await standingOf(documentOf(draft)));
    })();
  }, [draft]);

  const closeReview = useCallback((): void => {
    setMode("definition");
  }, []);

  const apply = useCallback(
    (plan: CompanyBundlePlan): void => {
      setApplied(ASKING);
      void (async (): Promise<void> => {
        setApplied(
          await ask(() =>
            commands.applyCompanyBundle({
              IdempotencyKey: commandKeyFor(plan.plan_digest),
              body: {
                bundle: documentOf(draft),
                expected_active_version: plan.base_version,
                plan_digest: plan.plan_digest,
              },
            })
          )
        );
      })();
    },
    [draft]
  );

  return {
    draft,
    setDraft,
    edits: editCount(draft),
    standing,
    mode,
    review,
    openReview,
    closeReview,
    armed,
    setArmed,
    applied,
    apply,
  };
}

/** Check and plan one document, and stop at the first thing that is not an answer. */
async function standingOf(bundle: CompanyBundleDocument): Promise<Answer<Standing>> {
  const validation = await ask(() => computations.validateCompanyBundle({ body: { bundle } }));
  if (validation.kind !== "answered") {
    return validation;
  }
  const plan = await ask(() => computations.planCompanyBundle({ body: { bundle } }));
  if (plan.kind !== "answered") {
    return plan;
  }
  return { kind: "answered", value: { validation: validation.value, plan: plan.value } };
}
