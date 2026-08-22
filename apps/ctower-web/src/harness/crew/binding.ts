import type { CompanyBundleAssignment, CompanyBundleDocument } from "@ctower/client";

/**
 * The profile half of a crew, expressed as the document the registry accepts.
 *
 * Binding a profile to a crew is an assignment and nothing more: the component
 * already exists, so the proposal carries the exact revision and digest the
 * export handed over and mints nothing. That is what keeps this a one-line
 * change to a bundle the browser could not otherwise author.
 */
export interface ProfileOption {
  readonly key: string;
  readonly revision: number;
  readonly digest: string;
}

const PROFILE_KIND = "agent_profile";
const PROFILE_SLOT = "agent_profile";
/** The namespace to put a new crew in when the record has stated no preference. */
const FALLBACK_PREFIX = "crew";

export function profilesOf(document: CompanyBundleDocument): readonly ProfileOption[] {
  return document.resources
    .filter((resource) => resource.component.kind === PROFILE_KIND)
    .map((resource) => ({
      key: resource.component.key,
      revision: resource.component.revision,
      digest: resource.component.content_digest,
    }));
}

/**
 * The namespace this company already puts its crew in.
 *
 * Read off the record rather than derived from the company key, because those
 * are different strings on a real tower — `ctower-development` keeps its crew
 * under `ctower:` — and inventing a second namespace would split the roster.
 */
export function crewPrefix(document: CompanyBundleDocument): string {
  const first = document.assignments.find(
    (assignment) => assignment.slot === PROFILE_SLOT && assignment.subject.includes(":")
  );
  return first === undefined ? FALLBACK_PREFIX : first.subject.slice(0, first.subject.indexOf(":"));
}

export function bindingFor(profile: ProfileOption, subject: string): CompanyBundleAssignment {
  return {
    subject,
    slot: PROFILE_SLOT,
    component: {
      kind: PROFILE_KIND,
      key: profile.key,
      revision: profile.revision,
      content_digest: profile.digest,
    },
  };
}

/** Whether the record already says exactly this, in which case nothing is written. */
export function boundAlready(
  document: CompanyBundleDocument,
  binding: CompanyBundleAssignment
): boolean {
  return document.assignments.some(
    (assignment) =>
      assignment.subject === binding.subject &&
      assignment.slot === binding.slot &&
      assignment.component.key === binding.component.key &&
      assignment.component.revision === binding.component.revision &&
      assignment.component.content_digest === binding.component.content_digest
  );
}

/**
 * The exported document with this crew bound, in place when the seat is already
 * taken and appended when it is not. Nothing else moves: every other resource,
 * assignment and secret reference is carried through byte for byte.
 */
export function withBinding(
  document: CompanyBundleDocument,
  binding: CompanyBundleAssignment
): CompanyBundleDocument {
  const held = (assignment: CompanyBundleAssignment): boolean =>
    assignment.subject === binding.subject && assignment.slot === binding.slot;
  const assignments = document.assignments.some(held)
    ? document.assignments.map((assignment) => (held(assignment) ? binding : assignment))
    : [...document.assignments, binding];
  return { ...document, assignments };
}
