import type {
  CompanyBundleDocument,
  CompanyBundlePlan,
  CompanyBundleValidationResult,
} from "@ctower/client";
import { ask, computations } from "../api/client";
import type { Answer } from "../api/client";

/**
 * What the registry says about one exact document.
 *
 * The document is part of the answer and not a lookup, because a plan is only
 * meaningful about the bytes it was computed from. Apply is handed a `Standing`
 * and sends `standing.document`, so the thing recorded is always the thing that
 * was read — never whatever the editor happens to hold when the button is
 * pressed.
 *
 * This lives on its own because there is one company bundle and one ceremony
 * over it. The Company page composes a document out of the company's identity
 * and the Workflows page composes one out of a workflow definition, and both
 * arrive here: check it, plan it, and let the operator read the registry's own
 * answer before anything is written.
 */
export interface Standing {
  readonly document: CompanyBundleDocument;
  readonly validation: CompanyBundleValidationResult;
  readonly plan: CompanyBundlePlan;
}

/** Check and plan one document, and stop at the first thing that is not an answer. */
export async function standingOf(bundle: CompanyBundleDocument): Promise<Answer<Standing>> {
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
