import { useEffect, useState } from "react";
import type { CompanyBundleExportResult } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * What the wizard starts from.
 *
 * `exportCompanyBundle` is asked once per `reloadKey`, and not before
 * `admitted`: the ask crosses the development server's admission gate, which
 * answers `/v1/...` with its own 401 while no token is held, so an ungated read
 * collects console errors before the operator has pasted anything. The hook
 * waits instead; when admission arrives it asks in that same pass. Callers
 * that only exist behind a gate may omit the flag.
 *
 * A bundle that is active seeds the draft with the exact document the API returned.
 * `bundle-not-active` is the one refusal that is not a refusal here — it is the
 * answer "there is no company yet", which is precisely the case this wizard exists
 * for — so it becomes the empty template. Every other refusal stays a refusal.
 */
export type Seed =
  | { readonly kind: "exported"; readonly result: CompanyBundleExportResult }
  | { readonly kind: "template" };

const NO_BUNDLE_YET = "bundle-not-active";

export function useSeed(reloadKey: number, admitted = true): Answer<Seed> {
  const [seed, setSeed] = useState<Answer<Seed>>(ASKING);

  useEffect(() => {
    if (!admitted) {
      return;
    }
    let live = true;
    const load = async (): Promise<void> => {
      const answer = await ask(() => reads.exportCompanyBundle({}));
      if (!live) {
        return;
      }
      setSeed(asSeed(answer));
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [reloadKey, admitted]);

  return seed;
}

function asSeed(answer: Answer<CompanyBundleExportResult>): Answer<Seed> {
  switch (answer.kind) {
    case "answered":
      return { kind: "answered", value: { kind: "exported", result: answer.value } };
    case "refused":
      return answer.problem.code === NO_BUNDLE_YET
        ? { kind: "answered", value: { kind: "template" } }
        : answer;
    case "asking":
    case "unreachable":
    case "malformed":
      return answer;
  }
}
