import { useCallback, useEffect, useRef, useState } from "react";
import type { CompanyBundleCommandResult } from "@ctower/client";
import type { Answer } from "../api/client";
import { useApply } from "./apply/useApply";
import { documentOf, draftFrom, EMPTY_TEMPLATE, editCount } from "./bundle";
import type { Draft } from "./bundle";
import { standingOf } from "./standing";
import type { Standing } from "./standing";
import type { Seed } from "./useSeed";

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
  const generation = useRef(0);
  const applying = useApply(generation, onApplied);

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

  const { forget } = applying;

  const setDraft = useCallback(
    (next: Draft): void => {
      supersede();
      setDraftState(next);
      setMode("definition");
      setReview(ASKING);
      setArmed(false);
      forget();
    },
    [forget, supersede]
  );

  const openReview = useCallback((): void => {
    const mine = supersede();
    const document = documentOf(draft);
    setMode("review");
    setReview(ASKING);
    setArmed(false);
    forget();
    void (async (): Promise<void> => {
      const answer = await standingOf(document);
      if (generation.current === mine) {
        setReview(answer);
      }
    })();
  }, [draft, forget, supersede]);

  /** Leaving clears the receipt; a stale one must not greet the next review. */
  const closeReview = useCallback((): void => {
    supersede();
    setMode("definition");
    setReview(ASKING);
    setArmed(false);
    forget();
  }, [forget, supersede]);

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
    applied: applying.applied,
    apply: applying.apply,
    retry: applying.retry,
  };
}
