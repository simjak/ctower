import type { CompanyBundleDocument, SeatCredentialReceipt } from "@ctower/client";

/**
 * The crew this company records, and the addresses this session minted.
 *
 * A crew is not a component. It is a subject the company binds an agent profile
 * to — `ctower:qa` carrying the `agent_profile` slot — so the roster is read off
 * the bundle's own assignments and no row here is invented.
 *
 * The address is the other half, and ctower serves no read for it. The authored
 * contract has `issueSeatCredential` and `revokeSeatCredential` and not one
 * operation that lists a seat, so the only addresses this screen can honestly
 * draw are the receipts it was handed. Every other row's address is unknown, and
 * unknown draws no mark.
 */
export interface Minted {
  /** The crew it was minted for, known because this screen is what minted it. */
  readonly subject: string;
  readonly receipt: SeatCredentialReceipt;
}

export interface CrewRow {
  readonly subject: string;
  /** The namespace the record puts this crew in, drawn quiet beside the name. */
  readonly prefix: string;
  readonly name: string;
  readonly profileKey: string;
  readonly address: SeatCredentialReceipt | null;
}

const PROFILE_SLOT = "agent_profile";
const PROJECT_KIND = "project";
const PROJECT_SUBJECT = "project:";

/**
 * The key an address can be issued against.
 *
 * `SeatCredentialIssueRequest.project_key` is narrower than either place the
 * company record names a project — no dots — so a project this company records
 * may still be unable to carry a seat. That is the record's own shape and the
 * screen shows it rather than dropping the row.
 */
const ADDRESSABLE = /^[a-z][a-z0-9-]{2,63}$/;

export interface ProjectOption {
  readonly key: string;
  /** Whether `SeatCredentialIssueRequest.project_key` accepts this key at all. */
  readonly addressable: boolean;
}

export function crewsOf(
  document: CompanyBundleDocument,
  minted: readonly Minted[]
): readonly CrewRow[] {
  return document.assignments
    .filter((assignment) => assignment.slot === PROFILE_SLOT)
    .map((assignment) => {
      const parts = splitSubject(assignment.subject);
      return {
        subject: assignment.subject,
        prefix: parts.prefix,
        name: parts.name,
        profileKey: assignment.component.key,
        address: addressFor(minted, assignment.subject),
      };
    });
}

/**
 * Every project this company records, as the record spells it.
 *
 * A company names a project in two places and they are not the same string: a
 * `project` component carries the document's key, and a `project:` subject
 * carries the key work is filed under. A project created on this screen's own
 * harness exists only as the first, so reading either one alone hides projects
 * that are really there — which is how a company with a brand new project ends
 * up being told it has none.
 *
 * Neither is checked by ctower. `issueSeatCredential` stores `project_key` on
 * the seat and validates nothing else about it, so this list is what the record
 * says exists and not a promise that an address will reach anything.
 */
export function recordedProjects(document: CompanyBundleDocument): readonly ProjectOption[] {
  const declared = document.resources
    .filter((resource) => resource.component.kind === PROJECT_KIND)
    .map((resource) => resource.component.key);
  const filedUnder = document.assignments
    .filter((assignment) => assignment.subject.startsWith(PROJECT_SUBJECT))
    .map((assignment) => assignment.subject.slice(PROJECT_SUBJECT.length));
  return [...new Set([...declared, ...filedUnder])]
    .sort()
    .map((key) => ({ key, addressable: ADDRESSABLE.test(key) }));
}

function splitSubject(subject: string): { readonly prefix: string; readonly name: string } {
  const colon = subject.indexOf(":");
  return colon < 0
    ? { prefix: "", name: subject }
    : { prefix: subject.slice(0, colon), name: subject.slice(colon + 1) };
}

/**
 * The last thing ctower said about this crew's address. A revocation receipt
 * carries the same credential and supersedes the issuance, so the newest answer
 * is the one that is true.
 */
function addressFor(minted: readonly Minted[], subject: string): SeatCredentialReceipt | null {
  const held = minted.filter((entry) => entry.subject === subject);
  return held.at(-1)?.receipt ?? null;
}
