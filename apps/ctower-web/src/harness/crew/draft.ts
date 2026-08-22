import type {
  CredentialScope,
  SecretBindingReference,
  SeatCredentialIssueRequest,
} from "@ctower/client";

/**
 * What defining a crew asks for, and the contract each answer has to meet.
 *
 * The patterns are the authored contract's own, restated here so the screen can
 * say what is still missing before it sends anything. They are not a second
 * validator: ctower checks all of this again and its refusal is the one that
 * counts. This only stops the operator finding out at the end of a round trip.
 *
 * Two of these fields are stricter than the contract on purpose, and both are
 * the same rule read twice:
 *
 * - The seat is asked for, never derived. `company-bundle.schema.json` says a
 *   seat key is "never inferred from subject or display text", and a screen that
 *   quietly fills one in from the crew's name is inventing exactly the join the
 *   record refuses to guess.
 * - The credential is a place, never a value. `credential_ref` is any string as
 *   far as the wire is concerned, which is wide enough to carry a secret, so
 *   this screen does not offer a field a secret would fit in: the class comes
 *   from the contract's own closed set and the rest has to be shaped like a
 *   path. A credential is a reference, and the reference is composed here rather
 *   than trusted from typing.
 */
export type ReferenceClass = SecretBindingReference["reference_class"];

/**
 * A place a credential lives, and the only string this screen will put in
 * `credential_ref`.
 *
 * It is a brand rather than a `string` because a check that can be skipped is
 * not a boundary. `referenceFor` is the one function that mints one, it mints
 * nothing from a locator outside the allowlist, and `issueBody` cannot be
 * called without one — so there is no path from a typed value to the wire, and
 * no future caller can add one by forgetting to validate.
 */
declare const REFERENCE: unique symbol;
export type CredentialReference = string & { readonly [REFERENCE]: true };

export interface CrewDraft {
  readonly name: string;
  readonly profileKey: string;
  readonly projectKey: string;
  readonly seatKey: string;
  readonly scopes: readonly CredentialScope[];
  readonly refClass: ReferenceClass;
  readonly refLocator: string;
  readonly fingerprint: string;
}

export const SCOPES: readonly CredentialScope[] = ["capture", "transition", "evidence"];

/** Where a credential is allowed to live, as the authored contract enumerates it. */
export const REFERENCE_CLASSES: readonly ReferenceClass[] = [
  "os-credential",
  "vault-path",
  "runtime-binding",
];

const NAME = /^[a-z][a-z0-9._-]*$/;
const SEAT = /^[a-z][a-z0-9._-]{1,95}$/;
const PROJECT = /^[a-z][a-z0-9-]{2,63}$/;
const FINGERPRINT = /^sha256:[0-9a-f]{64}$/;
/**
 * A locator names a place inside its class: lower case, at least two separated
 * segments, no segment longer than 31 characters, 64 characters in all.
 *
 * Every part of that is load-bearing against the one thing that must never
 * reach the record. A credential value is a single opaque token, so the
 * separator rule stops a bare one; base64, base64url, JWTs and `sk-` keys carry
 * upper case, so the case rule stops those; and the segment and total lengths
 * stop the obvious dodge of cutting a long token in half with a slash — 32 hex
 * characters do not fit in a segment and 64 do not fit in a locator.
 *
 * What it cannot do is prove that a short, lower-case, path-shaped string is not
 * a secret somebody went out of their way to format as one. No syntax can, and
 * guessing at entropy would be a denylist. This is the structural half; the
 * review showing the class and the place separately is the other half.
 */
const LOCATOR = /^(?=.{5,64}$)[a-z0-9][a-z0-9._-]{0,30}(\/[a-z0-9][a-z0-9._-]{0,30}){1,5}$/;

export function blankDraft(profileKey: string, projectKey: string): CrewDraft {
  return {
    name: "",
    profileKey,
    projectKey,
    seatKey: "",
    scopes: ["capture"],
    refClass: "vault-path",
    refLocator: "",
    fingerprint: "",
  };
}

/**
 * The reference ctower records: the class it belongs to, then the place in it.
 *
 * Null for anything the allowlist does not recognise as a place, which is the
 * whole point — a credential value has no reference to compose.
 */
export function referenceFor(draft: CrewDraft): CredentialReference | null {
  if (!LOCATOR.test(draft.refLocator)) {
    return null;
  }
  return `${draft.refClass}:${draft.refLocator}` as CredentialReference;
}

/**
 * The first thing standing between this draft and a command, in the operator's
 * words. One line, because the control it sits under is one control.
 */
export function unmet(draft: CrewDraft): string | null {
  if (!NAME.test(draft.name)) {
    return "A crew name is lower-case letters, digits, dot, dash or underscore.";
  }
  if (draft.profileKey === "") {
    return "A crew runs an agent profile. Choose the one it runs.";
  }
  if (!PROJECT.test(draft.projectKey)) {
    return "Choose a project whose key an address can carry.";
  }
  if (!SEAT.test(draft.seatKey)) {
    return "Name the seat this address is for. It is never taken from the crew's name.";
  }
  if (draft.scopes.length === 0) {
    return "An address with no scope can do nothing. Choose at least one.";
  }
  if (!LOCATOR.test(draft.refLocator)) {
    return "Name where the credential lives, as a path: acme/seat/engineer-3.";
  }
  if (!FINGERPRINT.test(draft.fingerprint)) {
    return "The fingerprint is sha256: and 64 hexadecimal characters.";
  }
  return null;
}

/**
 * The draft as the authored contract's own request.
 *
 * `display_name` is the crew's full subject, so the principal ctower creates
 * carries the name the company record already knows it by rather than a second
 * label invented at the boundary.
 */
export function issueBody(
  draft: CrewDraft,
  subject: string,
  reference: CredentialReference
): SeatCredentialIssueRequest {
  return {
    credential_digest: draft.fingerprint,
    credential_ref: reference,
    display_name: subject,
    project_key: draft.projectKey,
    scopes: draft.scopes,
    seat_key: draft.seatKey,
  };
}
