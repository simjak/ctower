import type { CompanyBundleDocument, CompanyBundleResource, ComponentKind } from "@ctower/client";

/**
 * The workflows a company declares, read out of the one document that carries
 * them.
 *
 * No operation in the authored contract returns a workflow. A workflow is a
 * component of the company definition, so the company definition is where this
 * page reads it — the same export the Company page seeds from, filtered by the
 * component's own `kind`.
 *
 * Every reader here is deliberately narrow. A field that is not the shape the
 * authored schema gives it is not rendered as one: it comes back `null` or
 * empty and the screen says the fact is absent, rather than showing a confident
 * wrong value. That is the whole difference between a console and a mock.
 */
export type ActivityClass = "work" | "verification";

export interface RoleFact {
  readonly plane: string;
  readonly key: string;
}

export interface StageFact {
  readonly key: string;
  /** `null` when the payload does not declare one of the two classes. */
  readonly activityClass: ActivityClass | null;
  readonly roles: readonly RoleFact[];
}

export interface TransitionFact {
  readonly from: string;
  readonly to: string;
  readonly predicate: string | null;
}

export interface RouteFact {
  readonly from: string;
  readonly to: string;
  readonly failureClass: string | null;
}

export interface WorkflowFact {
  readonly id: string;
  readonly key: string;
  /** The revision of the component in the definition. */
  readonly revision: number;
  readonly lifecycle: "draft" | "published" | "deprecated" | "revoked";
  readonly digest: string;
  readonly schemaRef: string;
  /** Null on a company-wide workflow; a key when it is scoped to one project. */
  readonly project: string | null;
  /** The workflow's own publication state, which is not the component's. */
  readonly status: string | null;
  readonly note: string | null;
  readonly initialStage: string | null;
  readonly inputContract: string | null;
  readonly terminalContract: string | null;
  readonly executionRef: string | null;
  readonly gatesRef: string | null;
  readonly stages: readonly StageFact[];
  readonly transitions: readonly TransitionFact[];
  readonly routes: readonly RouteFact[];
  /** Exactly what the record holds, for the operator who wants to read it. */
  readonly payload: Readonly<Record<string, unknown>>;
}

export function workflowFacts(document: CompanyBundleDocument): readonly WorkflowFact[] {
  return document.resources
    .filter((resource) => resource.component.kind === "workflow")
    .map(workflowFact);
}

/** The policy components a workflow points at, when this company declares them. */
export function policyResource(
  document: CompanyBundleDocument,
  kind: ComponentKind,
  reference: string | null
): CompanyBundleResource | null {
  if (reference === null) {
    return null;
  }
  const [key, revision] = splitReference(reference);
  return (
    document.resources.find(
      (resource) =>
        resource.component.kind === kind &&
        resource.component.key === key &&
        (revision === null || resource.component.revision === revision)
    ) ?? null
  );
}

/** `engineering.software-factory.gates@1` is a key and a revision, said once. */
export function splitReference(reference: string): readonly [string, number | null] {
  const match = /^(.*)@([1-9][0-9]*)$/.exec(reference);
  if (match === null) {
    return [reference, null];
  }
  return [match[1] ?? reference, Number(match[2])];
}

function workflowFact(resource: CompanyBundleResource): WorkflowFact {
  const component = resource.component;
  const payload = resource.payload;
  const policies = record(payload.policy_refs);
  return {
    id: `${component.key}:${String(component.revision)}`,
    key: component.key,
    revision: component.revision,
    lifecycle: component.lifecycle,
    digest: component.content_digest,
    schemaRef: component.schema_ref,
    project: component.scope.project,
    status: text(payload.status),
    note: text(payload.note),
    initialStage: text(payload.initial_stage),
    inputContract: text(payload.input_contract),
    terminalContract: text(payload.terminal_contract),
    executionRef: policies === null ? null : text(policies.execution),
    gatesRef: policies === null ? null : text(policies.gates),
    stages: list(payload.stages).map(stageFact).filter(isPresent),
    transitions: list(payload.transitions).map(transitionFact).filter(isPresent),
    routes: list(payload.failure_routes).map(routeFact).filter(isPresent),
    payload,
  };
}

function stageFact(value: unknown): StageFact | null {
  const stage = record(value);
  const key = stage === null ? null : text(stage.key);
  if (stage === null || key === null) {
    return null;
  }
  const activity = text(stage.activity_class);
  return {
    key,
    activityClass: activity === "work" || activity === "verification" ? activity : null,
    roles: list(stage.role_keys).map(roleFact).filter(isPresent),
  };
}

function roleFact(value: unknown): RoleFact | null {
  const role = record(value);
  const key = role === null ? null : text(role.key);
  const plane = role === null ? null : text(role.authority_plane);
  return key === null || plane === null ? null : { plane, key };
}

function transitionFact(value: unknown): TransitionFact | null {
  const transition = record(value);
  const from = transition === null ? null : text(transition.from);
  const to = transition === null ? null : text(transition.to);
  if (transition === null || from === null || to === null) {
    return null;
  }
  return { from, to, predicate: text(transition.predicate_ref) };
}

function routeFact(value: unknown): RouteFact | null {
  const route = record(value);
  const from = route === null ? null : text(route.from);
  const to = route === null ? null : text(route.to);
  if (route === null || from === null || to === null) {
    return null;
  }
  return { from, to, failureClass: text(route.failure_class_ref) };
}

function isPresent<T>(value: T | null): value is T {
  return value !== null;
}

function record(value: unknown): Readonly<Record<string, unknown>> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Readonly<Record<string, unknown>>)
    : null;
}

function list(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}
