import { useEffect, useState } from "react";
import type { CompanyBundleExportResult } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * What the wizard starts from.
 *
 * `exportCompanyBundle` is asked once. A bundle that is active seeds the draft
 * with the exact document the API returned. `bundle-not-active` is the one
 * refusal that is not a refusal here — it is the answer "there is no company
 * yet", which is precisely the case this wizard exists for — so it becomes the
 * empty template. Every other refusal stays a refusal.
 */
export type Seed =
  | { readonly kind: "exported"; readonly result: CompanyBundleExportResult }
  | { readonly kind: "template" };

const NO_BUNDLE_YET = "bundle-not-active";

export function useSeed(): Answer<Seed> {
  const [seed, setSeed] = useState<Answer<Seed>>(ASKING);

  useEffect(() => {
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
  }, []);

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
