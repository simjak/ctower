/**
 * The wizard's four steps, which are four real operations and nothing else.
 *
 * `compose` seeds from `exportCompanyBundle`; `validate`, `plan` and `apply`
 * are `validateCompanyBundle`, `planCompanyBundle` and `applyCompanyBundle`.
 * There is no review step, no summary step, and no confirmation page: a step
 * exists here only because the API has a call behind it.
 */
export type StepKey = "compose" | "validate" | "plan" | "apply";

export interface Step {
  readonly key: StepKey;
  /** The step's own number, drawn in the rail. */
  readonly ordinal: number;
  readonly label: string;
  /** The generated operation this step calls, shown in mono (D6). */
  readonly operation: string;
}

export const STEPS: readonly Step[] = [
  { key: "compose", ordinal: 1, label: "Compose", operation: "exportCompanyBundle" },
  { key: "validate", ordinal: 2, label: "Validate", operation: "validateCompanyBundle" },
  { key: "plan", ordinal: 3, label: "Plan", operation: "planCompanyBundle" },
  { key: "apply", ordinal: 4, label: "Apply", operation: "applyCompanyBundle" },
];

export function stepAt(index: number): Step {
  const step = STEPS[index];
  if (step === undefined) {
    throw new RangeError(`no wizard step at ${String(index)}`);
  }
  return step;
}
