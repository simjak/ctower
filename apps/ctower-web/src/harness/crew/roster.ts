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

/**
 * The key an address can be issued against.
 *
 * `SeatCredentialIssueRequest.project_key` is narrower than a project's own key
 * — no dots — so a project this company records may still be unable to carry a
 * seat. That is the record's shape, and the screen shows it rather than dropping
 * the row or reaching somewhere else for a key that would fit.
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
 * The projects this company declares, each under the key it declares itself by.
 *
 * One source, and it is the only one that is a project's own statement of its
 * key: a `project` component's authored `key` field. Nothing here is taken apart
 * from a subject. A `project:` assignment subject reads like it carries a
 * project key and it must not be mined for one — the authored contract's
 * position on that is explicit for the fields it does declare (`seat_key` and
 * `role_key` are "never inferred from subject or display text"), and a subject
 * is a subject.
 *
 * The cost of holding that line is real and is left visible rather than papered
 * over: a company whose projects are declared under dotted keys has no project
 * that can carry an address, and the screen says exactly that. See the defect
 * report in `coordination/designer-harness-crew.defect-assignment-join.md` —
 * the assignment fields that would carry this properly are declared by
 * `company-bundle.schema.json` and are absent from the HTTP contract, so no
 * browser can read or write them.
 */
export function recordedProjects(document: CompanyBundleDocument): readonly ProjectOption[] {
  const declared = document.resources
    .filter((resource) => resource.component.kind === PROJECT_KIND)
    .map((resource) => authoredKey(resource.payload) ?? resource.component.key);
  return [...new Set(declared)].sort().map((key) => ({ key, addressable: ADDRESSABLE.test(key) }));
}

/** `ctower.project/v1` carries its own `key`; the component's is the fallback. */
function authoredKey(payload: Readonly<Record<string, unknown>>): string | null {
  const key = payload.key;
  return typeof key === "string" && key !== "" ? key : null;
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
