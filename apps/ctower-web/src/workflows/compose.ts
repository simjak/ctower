import type {
  CompanyBundleAssignment,
  CompanyBundleDocument,
  CompanyBundleResource,
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
 * command under the operator's own authority.
 *
 * The digest is minted here the way the kernel mints it — RFC 8785 then
 * SHA-256 — and the registry recomputes it. A wrong byte is not a silent
 * failure: the bundle is refused at `digest.canonical`, which is exactly why a
 * browser is allowed to author a component at all.
 *
 * **A dependency pin is exact, so a revision moves everything that names it.**
 * A gate policy pins the workflow it gates by revision *and* digest, and this
 * tower's workflow pins those policies straight back. Revising the workflow
 * alone leaves those pins naming a revision the bundle no longer carries, and
 * the registry answers `bundle-reference-invalid` — which is what it did to the
 * first version of this file, on the live tower, before this closure existed.
 * So every component that names what moved moves with it, and the operator
 * reads the whole set in the plan before anything is applied.
 */
const SLOT = "workflow";

export function documentWith(
  base: CompanyBundleDocument,
  draft: WorkflowDraft
): CompanyBundleDocument {
  const revision = (draft.base?.revision ?? 0) + 1;
  const payload = payloadOf(draft, revision);
  const authored = mint(base, draft, payload, revision);
  const moved = closureOf(base, authored);
  const resolved = repointed(base, moved, { component: authored, payload });
  const kept = base.resources.filter((resource) => !moved.has(idOf(resource.component)));
  return {
    ...base,
    assignments: rebind(base.assignments, moved, draft, resolved),
    resources: [...kept, ...resolved.values()],
  };
}

/**
 * Everything this change moves: the authored workflow, and every component that
 * pins something already moving. A component moves at most once, so the loop
 * settles; its payload is untouched, so its digest is the one it already had
 * and only its revision and its pins change.
 */
function closureOf(
  base: CompanyBundleDocument,
  authored: VersionedComponent
): ReadonlyMap<string, ComponentReference> {
  const moved = new Map<string, ComponentReference>([[idOf(authored), referenceOf(authored)]]);
  let found = true;
  while (found) {
    found = false;
    for (const resource of base.resources) {
      const component = resource.component;
      if (moved.has(idOf(component))) {
        continue;
      }
      if (component.compatibility.requires.some((required) => moved.has(idOf(required)))) {
        moved.set(idOf(component), {
          content_digest: component.content_digest,
          key: component.key,
          kind: component.kind,
          revision: component.revision + 1,
        });
        found = true;
      }
    }
  }
  return moved;
}

/** Each moved component, rebuilt at its new revision with its pins re-aimed. */
function repointed(
  base: CompanyBundleDocument,
  moved: ReadonlyMap<string, ComponentReference>,
  authored: CompanyBundleResource
): ReadonlyMap<string, CompanyBundleResource> {
  const authoredId = idOf(authored.component);
  const built = new Map<string, CompanyBundleResource>([[authoredId, aimed(authored, moved)]]);
  for (const resource of base.resources) {
    const next = moved.get(idOf(resource.component));
    if (next === undefined || idOf(resource.component) === authoredId) {
      continue;
    }
    const carried = {
      ...resource,
      component: {
        ...resource.component,
        revision: next.revision,
        supersedes: referenceOf(resource.component),
      },
    };
    built.set(idOf(resource.component), aimed(carried, moved));
  }
  return built;
}

/** One component with every pin it holds re-aimed at what that pin now is. */
function aimed(
  resource: CompanyBundleResource,
  moved: ReadonlyMap<string, ComponentReference>
): CompanyBundleResource {
  return {
    ...resource,
    component: {
      ...resource.component,
      compatibility: {
        ...resource.component.compatibility,
        requires: resource.component.compatibility.requires.map(
          (required) => moved.get(idOf(required)) ?? required
        ),
      },
    },
  };
}

/**
 * The bindings. Every one that names a moved component is re-aimed at its new
 * revision, and the workflow's own set is rebuilt from the operator's choice of
 * projects — because an unticked project is a project this revision does not run
 * on, which is a decision and not an omission.
 */
function rebind(
  assignments: readonly CompanyBundleAssignment[],
  moved: ReadonlyMap<string, ComponentReference>,
  draft: WorkflowDraft,
  resolved: ReadonlyMap<string, CompanyBundleResource>
): readonly CompanyBundleAssignment[] {
  const authoredId = `workflow:${draft.key}`;
  const workflow = resolved.get(authoredId);
  const others = assignments
    .filter((assignment) => idOf(assignment.component) !== authoredId)
    .map((assignment) => ({
      ...assignment,
      component: moved.get(idOf(assignment.component)) ?? assignment.component,
    }));
  if (workflow === undefined) {
    return others;
  }
  const reference = referenceOf(workflow.component);
  return [
    ...others,
    ...draft.projects.map((project) => ({
      component: reference,
      slot: SLOT,
      subject: `project:${project}`,
    })),
  ];
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
    .map((resource) => referenceOf(resource.component));
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

function referenceOf(component: VersionedComponent): ComponentReference {
  return {
    content_digest: component.content_digest,
    key: component.key,
    kind: component.kind,
    revision: component.revision,
  };
}

/** A component's identity across revisions: what it is and what it is called. */
function idOf(reference: { readonly kind: string; readonly key: string }): string {
  return `${reference.kind}:${reference.key}`;
}

function blank(value: string): string | null {
  return value.length === 0 ? null : value;
}
