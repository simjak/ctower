import type { Answer } from "../api/client";
import type { Seed } from "../wizard/useSeed";

/**
 * A forced view, for proofing a screen whose real precondition cannot be
 * arranged on a live tower.
 *
 * `?preview=first-run` renders the empty-tower moment against a tower that has
 * a company, so the screen can be looked at without wiping a bundle to see it.
 *
 * Two rules keep this from becoming a lie:
 *
 * 1. It forces the **view**, never the wiring. Every control on a previewed
 *    screen calls the same operation with the same body it always would, and
 *    whatever ctower answers is what renders. Nothing is mocked.
 * 2. The header says `preview` for as long as one is forced, so a screenshot of
 *    a forced state can never be mistaken for a screenshot of a real one.
 *
 * It cannot write, and that is a property of the contract rather than of this
 * file: a company with no components fails `resources: minItems 1`, so the
 * check refuses before the command is ever reached.
 */
export type PreviewName = "first-run";

export function previewFromLocation(search: string): PreviewName | null {
  return new URLSearchParams(search).get("preview") === "first-run" ? "first-run" : null;
}

/** The seed a forced preview stands in for, or the real one. */
export function seedForPreview(preview: PreviewName | null, real: Answer<Seed>): Answer<Seed> {
  if (preview === null) {
    return real;
  }
  return { kind: "answered", value: { kind: "template" } };
}
