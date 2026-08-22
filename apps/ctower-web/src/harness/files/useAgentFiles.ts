import { useCallback, useEffect, useRef, useState } from "react";
import type {
  CompanyBundleCommandResult,
  CompanyBundleDocument,
  CompanyBundleResource,
} from "@ctower/client";
import { ask, ASKING, commands, computations } from "../../api/client";
import type { Answer } from "../../api/client";
import { commandKeyFor } from "../../wizard/apply/commandKey";
import type { Standing } from "../../wizard/useCompany";
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
  const [applied, setApplied] = useState<Answer<CompanyBundleCommandResult> | null>(null);
  const [sent, setSent] = useState<Standing | null>(null);
  const generation = useRef(0);

  const supersede = useCallback((): number => {
    generation.current += 1;
    return generation.current;
  }, []);

  const clear = useCallback((): void => {
    setMode("editing");
    setReview(ASKING);
    setArmed(false);
    setApplied(null);
    setSent(null);
  }, []);

  /**
   * A new recorded definition is the authority. The open file is re-read out of
   * it, so an accepted apply lands in the editor as the revision it produced
   * and the edits that produced it stop being edits.
   *
   * The receipt is deliberately left standing. The only thing that changes what
   * is recorded is an accepted apply, and clearing the screen on the way back
   * from one takes the command id, the digests and the version away at the
   * moment they are the whole point. The operator leaves the receipt.
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
        // Only acceptance changed what is recorded. `durability_pending` did
        // not, so nothing is re-read on it and the retry stays offered.
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
    applied,
    apply,
    retry,
  };
}

/**
 * Whether sending the same command again is the honest next move.
 *
 * A refusal is not: ctower read the command and said no, and re-sending it asks
 * the same question of the same answer. The other three are — the API was not
 * reached, its answer could not be read, or it took the command and has not
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
