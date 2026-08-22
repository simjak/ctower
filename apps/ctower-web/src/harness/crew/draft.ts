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
 * A locator names a place inside its class: lower-case segments, separated, at
 * least two of them. A credential value is a single opaque token — hex, base64,
 * a signed blob — and none of those are that shape, so this is a wall rather
 * than a warning about the one thing that must never reach the record.
 */
const LOCATOR = /^[a-z0-9][a-z0-9._-]{0,47}(\/[a-z0-9][a-z0-9._-]{0,47}){1,5}$/;

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

/** The reference ctower records: the class it belongs to, then the place in it. */
export function credentialReference(draft: CrewDraft): string {
  return `${draft.refClass}:${draft.refLocator}`;
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
export function issueBody(draft: CrewDraft, subject: string): SeatCredentialIssueRequest {
  return {
    credential_digest: draft.fingerprint,
    credential_ref: credentialReference(draft),
    display_name: subject,
    project_key: draft.projectKey,
    scopes: draft.scopes,
    seat_key: draft.seatKey,
  };
}
