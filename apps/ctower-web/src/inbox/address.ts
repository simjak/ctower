import type { InboxCorrespondent } from "@ctower/client";

/**
 * Who this console is, in the inbox, and who it may write to.
 *
 * Both facts come from the API and neither is inferred. The reader's own
 * address is whatever the thread list and the correspondent list call it, and
 * the addresses it may use are exactly the ones the correspondent list offers —
 * that list is defined as the set the send command accepts, so narrowing it
 * here, or widening it, would make the form promise something the command
 * refuses.
 */

/**
 * What the projection names a principal that holds no seat row.
 *
 * It is a sentinel, not a seat: an identity that can neither receive a message
 * nor address one. It arrives in the `recipient` and `sender` fields like any
 * other address, so a screen that does not know the word renders "unaddressable
 * has no threads" and calls an authority fact an empty inbox.
 */
export const UNADDRESSABLE = "unaddressable";

export function hasAddress(seat: string): boolean {
  return seat !== UNADDRESSABLE;
}

/**
 * Every message carries a project key, and no read returns the one an existing
 * thread was opened under. So the key is resolved from the correspondent list,
 * which is the only place the pairing (project, seat) is stated — and the
 * resolution has three honest outcomes, not one.
 */
export type Route =
  /** Exactly one project registers this seat: the message can name it. */
  | { readonly kind: "single"; readonly projectKey: string }
  /** Two projects register the same seat; the command refuses an ambiguous
   *  address, so the operator picks which of them this message is for. */
  | { readonly kind: "ambiguous"; readonly projectKeys: readonly string[] }
  /** The list does not offer this seat, so no key can be composed for it. */
  | { readonly kind: "unknown" };

export function routeTo(correspondents: readonly InboxCorrespondent[], seatKey: string): Route {
  const projectKeys = [
    ...new Set(
      correspondents
        .filter((correspondent) => correspondent.seat_key === seatKey)
        .map((correspondent) => correspondent.project_key)
    ),
  ].sort((left, right) => left.localeCompare(right));
  const only = projectKeys[0];
  if (only === undefined) {
    return { kind: "unknown" };
  }
  return projectKeys.length === 1
    ? { kind: "single", projectKey: only }
    : { kind: "ambiguous", projectKeys };
}

/** The seats this console may open a thread to, each named once. */
export function seatsOffered(correspondents: readonly InboxCorrespondent[]): readonly string[] {
  return [...new Set(correspondents.map((correspondent) => correspondent.seat_key))].sort(
    (left, right) => left.localeCompare(right)
  );
}
