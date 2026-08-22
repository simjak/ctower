import type {
  CompanyBundleAssignment,
  CompanyBundleDocument,
  ComponentReference,
  VersionedComponent,
} from "@ctower/client";
import { canonicalDigest } from "../mint/digest";
import { payloadOf } from "./draft";
import type { WorkflowDraft } from "./draft";
import { policyResource, splitReference } from "./read";

/**
 * The one function that turns a composed workflow back into the company
 * definition, because there is nowhere else for a workflow to live.
 *
 * The authored contract declares no operation that writes a workflow. A
 * workflow is a component of the company bundle, so authoring one is authoring
 * the bundle: the same document, the same check, the same plan, the same
 * command under the operator's own authority. This page adds one resource to
 * that document and repoints the bindings that named the revision it replaces.
 *
 * The digest is minted here the way the kernel mints it — RFC 8785 then
 * SHA-256 — and the registry recomputes it. A wrong byte is not a silent
 * failure: the bundle is refused at `digest.canonical`, which is exactly why a
 * browser is allowed to author a component at all.
 */
const SLOT = "workflow";

export function documentWith(
  base: CompanyBundleDocument,
  draft: WorkflowDraft
): CompanyBundleDocument {
  const revision = (draft.base?.revision ?? 0) + 1;
  const payload = payloadOf(draft, revision);
  const component = mint(base, draft, payload, revision);
  const reference: ComponentReference = {
    content_digest: component.content_digest,
    key: component.key,
    kind: component.kind,
    revision: component.revision,
  };
  const kept = base.resources.filter(
    (resource) => !(resource.component.kind === "workflow" && resource.component.key === draft.key)
  );
  return {
    ...base,
    assignments: rebind(base.assignments, draft, reference),
    resources: [...kept, { component, payload }],
  };
}

/**
 * The bindings that say which projects run this workflow.
 *
 * A binding names an exact revision and its digest, so a revision that is not
 * repointed leaves the record naming a component the bundle no longer carries.
 * Every binding for this workflow is therefore rebuilt from the operator's own
 * selection, and no other binding in the document is touched.
 */
function rebind(
  assignments: readonly CompanyBundleAssignment[],
  draft: WorkflowDraft,
  component: ComponentReference
): readonly CompanyBundleAssignment[] {
  const others = assignments.filter(
    (assignment) =>
      !(assignment.component.kind === "workflow" && assignment.component.key === draft.key)
  );
  const mine = draft.projects.map((project) => ({
    component,
    slot: SLOT,
    subject: `project:${project}`,
  }));
  return [...others, ...mine];
}

function mint(
  base: CompanyBundleDocument,
  draft: WorkflowDraft,
  payload: Readonly<Record<string, unknown>>,
  revision: number
): VersionedComponent {
  const digest = canonicalDigest(payload);
  const previous = draft.base;
  return {
    compatibility: { ctower: ">=0.0.0,<1.0.0", requires: requirements(base, draft) },
    content_digest: digest,
    key: draft.key,
    kind: "workflow",
    lifecycle: "published",
    payload_ref: `object:${digest}`,
    provenance: [{ digest, kind: "authored", source: "ctower-web/workflows" }],
    revision,
    schema: "ctower.versioned-component/v1",
    schema_ref: previous?.schemaRef ?? "ctower.workflow/v1",
    scope: { project: previous?.project ?? null, tenant: base.company.key },
    supersedes:
      previous === null
        ? null
        : {
            content_digest: previous.digest,
            key: previous.key,
            kind: "workflow",
            revision: previous.revision,
          },
  };
}

/**
 * What this workflow depends on, resolved out of the same definition rather
 * than restated. A policy reference this company does not declare produces no
 * requirement, because the digest that would pin it is not knowable here — and
 * the registry's own `reference.exact` check is what says so.
 */
function requirements(
  base: CompanyBundleDocument,
  draft: WorkflowDraft
): readonly ComponentReference[] {
  return [
    policyResource(base, "execution_policy", blank(draft.executionRef)),
    policyResource(base, "gate_policy", blank(draft.gatesRef)),
  ]
    .filter((resource) => resource !== null)
    .map((resource) => ({
      content_digest: resource.component.content_digest,
      key: resource.component.key,
      kind: resource.component.kind,
      revision: resource.component.revision,
    }));
}

/** The work-plane projects this company declares, by the record's own rule. */
export function projectKeys(base: CompanyBundleDocument): readonly string[] {
  const keys = base.resources
    .filter((resource) => resource.component.kind === "project")
    .map((resource) => splitReference(resource.component.key)[0].split(".")[0] ?? "");
  return [...new Set(keys.filter((key) => key.length > 0))].sort();
}

/** The projects a recorded workflow is bound to, read off the bindings. */
export function boundProjects(base: CompanyBundleDocument, workflowKey: string): readonly string[] {
  return base.assignments
    .filter(
      (assignment) =>
        assignment.component.kind === "workflow" && assignment.component.key === workflowKey
    )
    .map((assignment) => assignment.subject.split(":")[1] ?? assignment.subject)
    .sort();
}

function blank(value: string): string | null {
  return value.length === 0 ? null : value;
}
