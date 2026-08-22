import { useCallback, useState } from "react";
import type { CompanyBundleCommandResult } from "@ctower/client";
import { ask, commands } from "../../api/client";
import type { Answer } from "../../api/client";
import { commandKeyFor } from "./commandKey";
import type { Standing } from "../standing";

/**
 * The one command this browser can send, and everything that makes sending it
 * twice safe.
 *
 * `applyCompanyBundle` is the only write on this surface. It is the same act
 * whether the operator reached it from the company's identity or from a
 * workflow definition, so it is sent from one place: the exact document the
 * plan was computed from, under an idempotency key derived from that plan's own
 * digest, with the version the plan expected.
 */
export interface Applying {
  /** Absent until something has been sent. */
  readonly applied: Answer<CompanyBundleCommandResult> | null;
  readonly apply: (standing: Standing) => void;
  /**
   * Send the same command again, under the same idempotency key. Present only
   * once something has been sent and did not come back accepted — which is the
   * retry the receipt promises when the answer is "not known" or "not durable".
   */
  readonly retry: (() => void) | null;
  /** Forget what was sent, so a stale receipt cannot greet the next review. */
  readonly forget: () => void;
}

/**
 * @param generation the caller's own sequencing counter, read at send time. A
 * response that lands after the operator has moved on is dropped rather than
 * arriving on a screen that is no longer about it.
 * @param onAccepted called only on acceptance, because only acceptance changed
 * what is recorded. `durability_pending` did not.
 */
export function useApply(
  generation: { readonly current: number },
  onAccepted: () => void
): Applying {
  const [applied, setApplied] = useState<Answer<CompanyBundleCommandResult> | null>(null);
  const [sent, setSent] = useState<Standing | null>(null);

  const send = useCallback(
    (standing: Standing): void => {
      const mine = generation.current;
      setApplied({ kind: "asking" });
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
        if (answer.kind === "answered" && answer.value.durability_state === "accepted") {
          onAccepted();
        }
      })();
    },
    [generation, onAccepted]
  );

  const apply = useCallback(
    (standing: Standing): void => {
      setSent(standing);
      send(standing);
    },
    [send]
  );

  const forget = useCallback((): void => {
    setApplied(null);
    setSent(null);
  }, []);

  const retry =
    sent === null || applied === null || !resendable(applied)
      ? null
      : (): void => {
          send(sent);
        };

  return { applied, apply, retry, forget };
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
