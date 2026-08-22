import type { CredentialScope, SeatCredentialIssueRequest } from "@ctower/client";

/**
 * What defining a crew asks for, and the contract each answer has to meet.
 *
 * The patterns are the authored contract's own, restated here so the screen can
 * say what is still missing before it sends anything. They are not a second
 * validator: ctower checks all of this again and its refusal is the one that
 * counts. This only stops the operator finding out at the end of a round trip.
 *
 * The credential itself never appears. `SeatCredentialIssueRequest` asks for a
 * reference and a fingerprint, and that is exactly what this browser holds — the
 * secret stays with whoever custodies it, which is why this surface can mint an
 * address at all.
 */
export interface CrewDraft {
  readonly name: string;
  readonly profileKey: string;
  readonly projectKey: string;
  readonly seatKey: string;
  readonly scopes: readonly CredentialScope[];
  readonly credentialRef: string;
  readonly fingerprint: string;
}

export const SCOPES: readonly CredentialScope[] = ["capture", "transition", "evidence"];

const NAME = /^[a-z][a-z0-9._-]*$/;
const SEAT = /^[a-z][a-z0-9._-]{1,95}$/;
const FINGERPRINT = /^sha256:[0-9a-f]{64}$/;
const MAX_REF = 512;

export function blankDraft(profileKey: string, projectKey: string): CrewDraft {
  return {
    name: "",
    profileKey,
    projectKey,
    seatKey: "",
    scopes: ["capture"],
    credentialRef: "",
    fingerprint: "",
  };
}

/** The seat takes the crew's own name until the operator says otherwise. */
export function seatOf(draft: CrewDraft): string {
  return draft.seatKey === "" ? draft.name : draft.seatKey;
}

/**
 * The first thing standing between this draft and a command, in the operator's
 * words. One line, because the control it sits under is one control.
 */
export function unmet(draft: CrewDraft): string | null {
  if (!NAME.test(draft.name)) {
    return "A crew name is lower-case letters, digits, dot, dash or underscore.";
  }
  if (draft.profileKey === "" || draft.projectKey === "") {
    return "A crew needs a profile to run and a project to work in.";
  }
  if (!SEAT.test(seatOf(draft))) {
    return "The seat name is outside what ctower accepts.";
  }
  if (draft.scopes.length === 0) {
    return "An address with no scope can do nothing. Choose at least one.";
  }
  if (draft.credentialRef === "" || draft.credentialRef.length > MAX_REF) {
    return "Name where the credential lives, as a reference.";
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
    credential_ref: draft.credentialRef,
    display_name: subject,
    project_key: draft.projectKey,
    scopes: draft.scopes,
    seat_key: seatOf(draft),
  };
}
