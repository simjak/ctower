import { useCallback, useRef, useState } from "react";
import type { CompanyBundleCommandResult, CompanyBundleDocument } from "@ctower/client";
import type { Answer } from "../api/client";
import { standingOf } from "./standing";
import type { Standing } from "./standing";
import { useApply } from "./useApply";

/**
 * What a screen that authors is handed: what is recorded, whose tenant it is,
 * and the one way to change it. A surface composes the next document out of the
 * recorded one and hands it over; from there every one of them meets the same
 * check, the same plan, and the same operator-authority apply.
 */
export interface Authoring {
  readonly recorded: CompanyBundleDocument;
  /** The company key every component minted against it is scoped to. */
  readonly tenant: string;
  readonly propose: (next: CompanyBundleDocument) => void;
}

export interface Ceremony {
  readonly authoring: Authoring;
  /** Null until something is proposed; there is no review of nothing. */
  readonly review: Answer<Standing> | null;
  readonly applied: Answer<CompanyBundleCommandResult> | null;
  readonly armed: boolean;
  readonly setArmed: (armed: boolean) => void;
  readonly apply: (standing: Standing) => void;
  /** Present only when the same command may honestly be sent again. */
  readonly retry: (() => void) | null;
  readonly close: () => void;
}

const ASKING = { kind: "asking" } as const;

/**
 * Check, plan, apply — held once for every screen that writes to the company.
 *
 * The check-plan and the command itself are the shared ones: there is one
 * company bundle and one ceremony over it, so a screen reaches for `standingOf`
 * and `useApply` rather than keeping a second copy of the only write this
 * browser can send. Two screens author projects and agents into the same
 * document; two copies of this would be two ways for them to disagree.
 *
 * What this owns is the sequencing. The operator can leave the review or
 * propose something else while a plan is out, so each asynchronous act carries
 * the generation it started in and a response from a superseded generation is
 * dropped rather than arming an apply for a document nobody is looking at.
 */
export function useCeremony(recorded: CompanyBundleDocument, onApplied: () => void): Ceremony {
  const [review, setReview] = useState<Answer<Standing> | null>(null);
  const [armed, setArmed] = useState(false);
  const generation = useRef(0);
  const { applied, apply, retry, forget } = useApply(generation, onApplied);

  const supersede = useCallback((): number => {
    generation.current += 1;
    return generation.current;
  }, []);

  const propose = useCallback(
    (next: CompanyBundleDocument): void => {
      const mine = supersede();
      setReview(ASKING);
      setArmed(false);
      forget();
      void (async (): Promise<void> => {
        const answer = await standingOf(next);
        if (generation.current === mine) {
          setReview(answer);
        }
      })();
    },
    [forget, supersede]
  );

  const close = useCallback((): void => {
    supersede();
    setReview(null);
    setArmed(false);
    forget();
  }, [forget, supersede]);

  return {
    authoring: { recorded, tenant: recorded.company.key, propose },
    review,
    applied,
    armed,
    setArmed,
    apply,
    retry,
    close,
  };
}
