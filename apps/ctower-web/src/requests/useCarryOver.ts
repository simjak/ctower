import { useEffect, useState } from "react";
import type { CtowerProjectCutoverHealth } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * Why the ledger is empty, asked only when it is.
 *
 * An empty list is a fact; the reason for it is a different fact, and this
 * screen may not invent one. ctower records the reason — the legacy Request
 * ledger is carried over in one signed cutover, and until that cutover
 * completes a tenant that predates it cannot take a native capture at all — and
 * `getCtowerProjectCutoverHealth` is where that state is readable.
 *
 * So the second read happens exactly when the first one returns nothing, and
 * its answer is the only thing allowed to explain the emptiness. If it refuses
 * or says nothing, the screen says less rather than guessing.
 */
export function useCarryOver(asking: boolean): Answer<CtowerProjectCutoverHealth> {
  const [answer, setAnswer] = useState<Answer<CtowerProjectCutoverHealth>>(ASKING);

  useEffect(() => {
    if (!asking) {
      return;
    }
    let live = true;
    const load = async (): Promise<void> => {
      const next = await ask(() => reads.getCtowerProjectCutoverHealth({}));
      if (live) {
        setAnswer(next);
      }
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [asking]);

  return answer;
}

/**
 * Whether a Request can be filed at all, as the cutover read states it.
 *
 * The carry-over ends at the committed development epoch; every phase before
 * that one leaves native capture fenced. "The read did not say" is deliberately
 * not expressible here — that case is the answer's own `refused` or
 * `unreachable`, which the caller settles before it ever reaches this function.
 */
export function captureOpen(health: CtowerProjectCutoverHealth): boolean {
  return health.phase === "development_epoch_committed" || health.phase === "disaster_safe_active";
}
