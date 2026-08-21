/**
 * The four steps, named as the operator's own jobs.
 *
 * A step is never named after the call behind it. `exportCompanyBundle` is a
 * fact about this repository's contract, not a thing an operator does, and a
 * screen that prints it has put the API's vocabulary in front of the reader's.
 */
export type StepKey = "company" | "check" | "review" | "apply";

export interface Step {
  readonly key: StepKey;
  readonly ordinal: number;
  readonly label: string;
}

export const STEPS: readonly Step[] = [
  { key: "company", ordinal: 1, label: "Company details" },
  { key: "check", ordinal: 2, label: "Check the bundle" },
  { key: "review", ordinal: 3, label: "Review changes" },
  { key: "apply", ordinal: 4, label: "Apply" },
];
