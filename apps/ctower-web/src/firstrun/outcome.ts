import type { CompanyBundleCommandResult } from "@ctower/client";
import type { Answer } from "../api/client";

/**
 * What pressing the last button produced.
 *
 * A forced preview stops after the plan, so it needs an outcome of its own
 * rather than borrowing `asking` — a screen that says "working" forever is a
 * screen that lies about what happened.
 */
export type FirstRunOutcome = Answer<CompanyBundleCommandResult> | { readonly kind: "previewed" };
