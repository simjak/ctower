import type { Answer } from "../api/client";
import type { Seed } from "./useSeed";

/**
 * What this screen is, said truthfully.
 *
 * A tenant that already has an active company is not creating one, and calling
 * the screen "Create a company" in front of an operator who is looking at his
 * own company of two versions' standing is the fastest way to make him distrust
 * every other word on it. Until the read answers, neither mode is claimed.
 */
export function modeTitle(seed: Answer<Seed>): string {
  if (seed.kind !== "answered") {
    return "Company";
  }
  return seed.value.kind === "exported" ? "Edit company definition" : "Create a company";
}

/** The one line that says what the screen is for. One line, and no second one. */
export const PURPOSE =
  "Declare projects, agents, and seats. Review the exact changes before anything applies.";
