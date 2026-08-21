/**
 * What the inbox is, and what it says when it has no address.
 *
 * Both facts were authored twice — once in the screen and once in the compose
 * surface — and drifted apart in wording while claiming the same thing. They are
 * one vocabulary, so they live in one module.
 *
 * The plane line is the whole of what this surface says about its own scope. The
 * inbox is **transport**: `sendInboxMessage` and `ingestInboxNotification` never
 * evaluate a project grant, so the address book spans the tenant rather than the
 * project a reader arrived from. That is a real property an operator can be
 * caught out by, and D9 gives it one line and no more — the picker beside it
 * carries the same fact structurally by grouping seats under their projects.
 */

/** The record's own name for a principal that holds no seat row. */
export const UNADDRESSABLE = "unaddressable";

/** What mints a principal with a seat row — the one action that gives it an address. */
export const SEAT_COMMAND = "ctowerctl credential seat issue";

/** The one line this surface spends on its own scope. */
export const PLANE_HINT = "Every seat in the tenant, not one project.";

/** Why, on the hint's own `(i)`: one line, per D9. */
export const PLANE_WHY = "a send never evaluates a project grant";

const NO_ADDRESS = "This server holds no seat, so it has no address.";
const NO_SEATS = "The record lists no seat to write to.";

/** Why nothing can be addressed: no address to write from, or nobody to write to. */
export function addresslessReason(sender: string): string {
  return sender === UNADDRESSABLE ? NO_ADDRESS : NO_SEATS;
}
