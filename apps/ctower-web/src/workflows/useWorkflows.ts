import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CompanyBundleCommandResult, CompanyBundleDocument } from "@ctower/client";
import type { Answer } from "../api/client";
import { useApply } from "../wizard/apply/useApply";
import { standingOf } from "../wizard/standing";
import type { Standing } from "../wizard/standing";
import { boundProjects, documentWith } from "./compose";
import { draftOf, editCount, newDraft } from "./draft";
import type { WorkflowDraft } from "./draft";
import { workflowFacts } from "./read";
import type { WorkflowFact } from "./read";

/**
 * The page's one piece of state, and the ceremony it opens onto.
 *
 * Reading is free: the workflows are already in the definition this console
 * read at startup, so looking at one costs no call. Changing one is the company
 * bundle's own ceremony — check, plan, and a command under the operator's
 * authority — and it is not entered until the operator has actually changed
 * something.
 *
 * Every read is sequenced by a generation counter. A check-and-plan is two
 * round trips and the operator can go back, edit again, or apply during either
 * of them, so an answer from a superseded generation is dropped rather than
 * arming a command for a document nobody is looking at.
 */
export type Mode = "view" | "edit" | "review";

export interface Workflows {
  readonly declared: readonly WorkflowFact[];
  readonly here: WorkflowFact | null;
  readonly select: (id: string) => void;
  readonly mode: Mode;
  /** Present only while composing; there is no draft to hold otherwise. */
  readonly draft: WorkflowDraft | null;
  readonly setDraft: (draft: WorkflowDraft) => void;
  readonly edits: number;
  readonly revise: () => void;
  readonly add: () => void;
  readonly cancel: () => void;
  readonly openReview: () => void;
  readonly closeReview: () => void;
  readonly review: Answer<Standing>;
  readonly armed: boolean;
  readonly setArmed: (armed: boolean) => void;
  readonly applied: Answer<CompanyBundleCommandResult> | null;
  readonly apply: (standing: Standing) => void;
  readonly retry: (() => void) | null;
}

const ASKING = { kind: "asking" } as const;

export function useWorkflows(document: CompanyBundleDocument, onApplied: () => void): Workflows {
  const declared = useMemo(() => workflowFacts(document), [document]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("view");
  const [draft, setDraftState] = useState<WorkflowDraft | null>(null);
  const [review, setReview] = useState<Answer<Standing>>(ASKING);
  const [armed, setArmed] = useState(false);
  const generation = useRef(0);
  const applying = useApply(generation, onApplied);
  const { forget } = applying;

  const here = declared.find((workflow) => workflow.id === chosen) ?? declared[0] ?? null;

  /** A new recorded definition is the authority; anything composed on the old one goes. */
  useEffect(() => {
    generation.current += 1;
    setMode("view");
    setDraftState(null);
    setReview(ASKING);
    setArmed(false);
    forget();
  }, [document, forget]);

  const compose = useCallback(
    (next: WorkflowDraft): void => {
      generation.current += 1;
      setDraftState(next);
      setMode("edit");
      setReview(ASKING);
      setArmed(false);
      forget();
    },
    [forget]
  );

  const revise = useCallback((): void => {
    if (here !== null) {
      compose(draftOf(here, boundProjects(document, here.key)));
    }
  }, [compose, document, here]);

  const add = useCallback((): void => {
    compose(newDraft());
  }, [compose]);

  const cancel = useCallback((): void => {
    generation.current += 1;
    setMode("view");
    setDraftState(null);
    setReview(ASKING);
    setArmed(false);
    forget();
  }, [forget]);

  const openReview = useCallback((): void => {
    if (draft === null) {
      return;
    }
    generation.current += 1;
    const mine = generation.current;
    const composed = documentWith(document, draft);
    setMode("review");
    setReview(ASKING);
    setArmed(false);
    forget();
    void (async (): Promise<void> => {
      const answer = await standingOf(composed);
      if (generation.current === mine) {
        setReview(answer);
      }
    })();
  }, [document, draft, forget]);

  const closeReview = useCallback((): void => {
    generation.current += 1;
    setMode("edit");
    setReview(ASKING);
    setArmed(false);
    forget();
  }, [forget]);

  return {
    declared,
    here,
    select: setChosen,
    mode,
    draft,
    setDraft: setDraftState,
    edits: draft === null ? 0 : editCount(draft),
    revise,
    add,
    cancel,
    openReview,
    closeReview,
    review,
    armed,
    setArmed,
    applied: applying.applied,
    apply: applying.apply,
    retry: applying.retry,
  };
}
