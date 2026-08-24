import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CompanyBundleCommandResult,
  CompanyBundleDocument,
  CompanyBundleResource,
} from "@ctower/client";
import { ASKING } from "../../api/client";
import type { Answer } from "../../api/client";
import { standingOf } from "../../wizard/standing";
import type { Standing } from "../../wizard/standing";
import { useApply } from "../../wizard/useApply";
import { documentWith, draftOf, isEdited } from "./compose";
import type { FileDraft } from "./compose";
import { idOf, resourceById } from "./read";

/**
 * Editing one file, and the ceremony that edit produces.
 *
 * There is no stepper. A file is open or it is not; the moment its payload
 * differs from what is recorded the way forward appears, and the moment it
 * stops differing it goes away again. Review is not a step an operator walks
 * through to discover that nothing changed — the digest already answered that.
 *
 * The ceremony itself is not this screen's. `standingOf` checks and plans one
 * document and `useApply` sends the one command this browser can send, under an
 * idempotency key derived from the plan's own digest. There is one company
 * bundle and one act that writes it, so editing an agent file is the same act
 * the Company page and the Workflows page perform, entered from a different
 * screen.
 *
 * Every read is sequenced. A check-and-plan is two round trips and the operator
 * can keep typing, open another file, or apply during either of them, so each
 * read carries the generation it started in and an answer from a superseded
 * generation is dropped. Without that, a slow plan for an abandoned draft can
 * land in the review panel and arm an apply for a document nobody is looking
 * at.
 */
export type Mode = "editing" | "review";

export interface AgentFiles {
  readonly files: readonly CompanyBundleResource[];
  readonly openId: string | null;
  readonly open: (id: string) => void;
  readonly draft: FileDraft | null;
  readonly setDraft: (draft: FileDraft) => void;
  readonly edited: boolean;
  readonly mode: Mode;
  readonly review: Answer<Standing>;
  readonly openReview: () => void;
  readonly closeReview: () => void;
  readonly armed: boolean;
  readonly setArmed: (armed: boolean) => void;
  readonly applied: Answer<CompanyBundleCommandResult> | null;
  readonly apply: (standing: Standing) => void;
  /**
   * Send the same command again, under the same idempotency key. Present only
   * once something has been sent and did not come back accepted.
   */
  readonly retry: (() => void) | null;
}

export function useAgentFiles(
  document: CompanyBundleDocument,
  files: readonly CompanyBundleResource[],
  onApplied: () => void
): AgentFiles {
  const [draft, setDraftState] = useState<FileDraft | null>(null);
  const [mode, setMode] = useState<Mode>("editing");
  const [review, setReview] = useState<Answer<Standing>>(ASKING);
  const [armed, setArmed] = useState(false);
  const generation = useRef(0);
  const applying = useApply(generation, onApplied);
  const { forget } = applying;

  const supersede = useCallback((): number => {
    generation.current += 1;
    return generation.current;
  }, []);

  const clear = useCallback((): void => {
    setMode("editing");
    setReview(ASKING);
    setArmed(false);
    forget();
  }, [forget]);

  /**
   * A new recorded definition is the authority. The open file is re-read out of
   * it, so an accepted apply lands in the editor as the revision it produced
   * and the edits that produced it stop being edits.
   *
   * The receipt is deliberately left standing: `forget` is not called here. The
   * only thing that changes what is recorded is an accepted apply, and clearing
   * the screen on the way back from one takes the command id, the digests and
   * the version away at the moment they are the whole point. The operator leaves
   * the receipt.
   */
  useEffect(() => {
    setDraftState((held) => {
      const again = held === null ? null : resourceById(document, idOf(held.base.component));
      return again === null ? null : draftOf(again);
    });
  }, [document]);

  const open = useCallback(
    (id: string): void => {
      supersede();
      clear();
      const resource = resourceById(document, id);
      setDraftState(resource === null ? null : draftOf(resource));
    },
    [document, supersede, clear]
  );

  const setDraft = useCallback(
    (next: FileDraft): void => {
      supersede();
      clear();
      setDraftState(next);
    },
    [supersede, clear]
  );

  const openReview = useCallback((): void => {
    if (draft === null) {
      return;
    }
    const mine = supersede();
    clear();
    setMode("review");
    void (async (): Promise<void> => {
      const answer = await standingOf(documentWith(document, draft));
      if (generation.current === mine) {
        setReview(answer);
      }
    })();
  }, [document, draft, supersede, clear]);

  const closeReview = useCallback((): void => {
    supersede();
    clear();
  }, [supersede, clear]);

  return {
    files,
    openId: draft === null ? null : idOf(draft.base.component),
    open,
    draft,
    setDraft,
    edited: draft !== null && isEdited(draft),
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
