import { useCallback, useEffect, useRef, useState } from "react";
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

/**
 * What the registry says about one exact document.
 *
 * The document is part of the answer and not a lookup, because a plan is only
 * meaningful about the bytes it was computed from. Apply is handed a `Standing`
 * and sends `standing.document`, so the thing recorded is always the thing that
 * was read — never whatever the editor happens to hold when the button is
 * pressed.
 */
export interface Standing {
  readonly document: CompanyBundleDocument;
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
  readonly apply: (standing: Standing) => void;
  /**
   * Send the same command again, under the same idempotency key. Present only
   * once something has been sent and did not come back accepted — which is the
   * retry the receipt promises when the answer is "not known" or "not durable".
   */
  readonly retry: (() => void) | null;
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
 *
 * Every read here is sequenced. A check-and-plan is two round trips and the
 * operator can edit, leave, or apply during either of them, so each read carries
 * the generation it was started in and a response from a superseded generation
 * is dropped. Without that, a slow plan for an abandoned draft can land in the
 * review panel and arm an apply for a document nobody is looking at.
 */
export function useCompany(seed: Seed, onApplied: () => void): Company {
  const recorded = seed.kind === "exported" ? seed.result.bundle : EMPTY_TEMPLATE;
  const [draft, setDraftState] = useState<Draft>(() => draftFrom(recorded));
  const [standing, setStanding] = useState<Answer<Standing>>(ASKING);
  const [mode, setMode] = useState<Mode>("definition");
  const [review, setReview] = useState<Answer<Standing>>(ASKING);
  const [armed, setArmed] = useState(false);
  const [applied, setApplied] = useState<Answer<CompanyBundleCommandResult> | null>(null);
  const [sent, setSent] = useState<Standing | null>(null);
  const generation = useRef(0);

  const supersede = useCallback((): number => {
    generation.current += 1;
    return generation.current;
  }, []);

  /**
   * A new recorded state is the authority, and it replaces the draft built on
   * the old one. This is what makes an accepted apply land in the editor: the
   * page re-reads, and the edits that produced the apply stop being edits.
   */
  useEffect(() => {
    const mine = supersede();
    setDraftState(draftFrom(recorded));
    setStanding(ASKING);
    void (async (): Promise<void> => {
      const answer = await standingOf(recorded);
      if (generation.current === mine) {
        setStanding(answer);
      }
    })();
  }, [recorded, supersede]);

  const setDraft = useCallback(
    (next: Draft): void => {
      supersede();
      setDraftState(next);
      setMode("definition");
      setReview(ASKING);
      setArmed(false);
      setApplied(null);
      setSent(null);
    },
    [supersede]
  );

  const openReview = useCallback((): void => {
    const mine = supersede();
    const document = documentOf(draft);
    setMode("review");
    setReview(ASKING);
    setApplied(null);
    setArmed(false);
    setSent(null);
    void (async (): Promise<void> => {
      const answer = await standingOf(document);
      if (generation.current === mine) {
        setReview(answer);
      }
    })();
  }, [draft, supersede]);

  /** Leaving clears the receipt; a stale one must not greet the next review. */
  const closeReview = useCallback((): void => {
    supersede();
    setMode("definition");
    setReview(ASKING);
    setArmed(false);
    setApplied(null);
    setSent(null);
  }, [supersede]);

  /**
   * One command, and the exact document it was reviewed against. The
   * idempotency key comes from the plan digest, so a retry of this standing is
   * the same command and can never write twice.
   */
  const send = useCallback(
    (standing: Standing): void => {
      const mine = generation.current;
      setApplied(ASKING);
      void (async (): Promise<void> => {
        const answer = await ask(() =>
          commands.applyCompanyBundle({
            IdempotencyKey: commandKeyFor(standing.plan.plan_digest),
            body: {
              bundle: standing.document,
              expected_active_version: standing.plan.base_version,
              plan_digest: standing.plan.plan_digest,
            },
          })
        );
        if (generation.current !== mine) {
          return;
        }
        setApplied(answer);
        // Only acceptance changed what is recorded. `durability_pending` did not,
        // so nothing is re-read on it and the retry stays offered.
        if (answer.kind === "answered" && answer.value.durability_state === "accepted") {
          onApplied();
        }
      })();
    },
    [onApplied]
  );

  const apply = useCallback(
    (standing: Standing): void => {
      setSent(standing);
      send(standing);
    },
    [send]
  );

  const retry =
    sent === null || applied === null || !resendable(applied)
      ? null
      : (): void => {
          send(sent);
        };

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
    retry,
  };
}

/**
 * Whether sending the same command again is the honest next move.
 *
 * A refusal is not: ctower read the command and said no, and re-sending it
 * asks the same question of the same answer. The other three are — the API was
 * not reached, its answer could not be read, or it took the command and has not
 * confirmed it is durable. In every one of those the operator does not know
 * what was written, and the shared idempotency key is what makes finding out
 * safe.
 */
function resendable(applied: Answer<CompanyBundleCommandResult>): boolean {
  switch (applied.kind) {
    case "asking":
    case "refused":
      return false;
    case "unreachable":
    case "malformed":
      return true;
    case "answered":
      return applied.value.durability_state !== "accepted";
  }
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
  return {
    kind: "answered",
    value: { document: bundle, validation: validation.value, plan: plan.value },
  };
}
