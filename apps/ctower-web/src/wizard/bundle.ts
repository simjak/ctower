import type {
  CompanyBundleAssignment,
  CompanyBundleDocument,
  CompanyBundleResource,
  ComponentKind,
} from "@ctower/client";

/**
 * The draft the operator is composing, and the one function that turns it back
 * into the authored contract's own document.
 *
 * A draft is deliberately not a second bundle model. It is the exported
 * document plus exactly the two edits this browser can honestly own: the
 * company's identity, and which authored components are in. Everything else —
 * every digest, revision, payload and compatibility record — is carried through
 * byte for byte from the answer the API gave, because the browser cannot mint a
 * canonical component digest and must never appear to.
 */
export interface Draft {
  /** The exported document, or the empty template when no bundle is active. */
  readonly base: CompanyBundleDocument;
  readonly companyKey: string;
  readonly displayName: string;
  /** Component references the operator has taken out, by `componentId`. */
  readonly dropped: ReadonlySet<string>;
}

export const EMPTY_TEMPLATE: CompanyBundleDocument = {
  schema: "ctower.company-bundle/v1",
  company: { key: "", display_name: "" },
  resources: [],
  assignments: [],
  secret_binding_refs: [],
};

export function draftFrom(base: CompanyBundleDocument): Draft {
  return {
    base,
    companyKey: base.company.key,
    displayName: base.company.display_name,
    dropped: new Set<string>(),
  };
}

export function componentId(reference: {
  readonly kind: ComponentKind;
  readonly key: string;
  readonly revision: number;
}): string {
  return `${reference.kind}:${reference.key}:${String(reference.revision)}`;
}

/** The draft as the authored contract's own document, ready to send. */
export function documentOf(draft: Draft): CompanyBundleDocument {
  const resources = draft.base.resources.filter(
    (resource) => !draft.dropped.has(componentId(resource.component))
  );
  const assignments = draft.base.assignments.filter(
    (assignment) => !draft.dropped.has(componentId(assignment.component))
  );
  return {
    ...draft.base,
    company: { key: draft.companyKey, display_name: draft.displayName },
    resources,
    assignments,
  };
}

export function isEdited(draft: Draft): boolean {
  return (
    draft.dropped.size > 0 ||
    draft.companyKey !== draft.base.company.key ||
    draft.displayName !== draft.base.company.display_name
  );
}

export type GroupKey = "projects" | "agents" | "rest";

export interface Group {
  readonly key: GroupKey;
  readonly label: string;
  readonly resources: readonly CompanyBundleResource[];
}

const AGENT_KINDS: ReadonlySet<ComponentKind> = new Set<ComponentKind>([
  "agent_profile",
  "persona",
]);

/**
 * The bundle read as three kinds of document: the projects, the agents, and
 * everything else the company is made of. The grouping is by the component's
 * own `kind`, never by a name.
 */
export function groupsOf(document: CompanyBundleDocument): readonly Group[] {
  const projects: CompanyBundleResource[] = [];
  const agents: CompanyBundleResource[] = [];
  const rest: CompanyBundleResource[] = [];
  for (const resource of document.resources) {
    if (resource.component.kind === "project") {
      projects.push(resource);
    } else if (AGENT_KINDS.has(resource.component.kind)) {
      agents.push(resource);
    } else {
      rest.push(resource);
    }
  }
  return [
    { key: "projects", label: "Projects", resources: projects },
    { key: "agents", label: "Agents", resources: agents },
    { key: "rest", label: "Components", resources: rest },
  ];
}

/** The subjects an authored component is bound to, for the row that draws it. */
export function subjectsOf(
  assignments: readonly CompanyBundleAssignment[],
  resource: CompanyBundleResource
): readonly string[] {
  const id = componentId(resource.component);
  return assignments
    .filter((assignment) => componentId(assignment.component) === id)
    .map((assignment) => assignment.subject);
}

/** A digest, shortened for a screen; the full value stays in the `title`. */
export function shortDigest(digest: string): string {
  const body = digest.startsWith("sha256:") ? digest.slice(7) : digest;
  return `${digest.startsWith("sha256:") ? "sha256:" : ""}${body.slice(0, 12)}…`;
}
