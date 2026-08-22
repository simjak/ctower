import type { ReactElement } from "react";
import type { CompanyBundleDocument, CompanyBundleResource, ComponentKind } from "@ctower/client";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { shortDigest } from "../wizard/bundle";
import { policyResource } from "./read";
import type { WorkflowFact } from "./read";

/**
 * What the workflow runs under: the shape of work it takes in, the shape it
 * ends at, and the two policies it names.
 *
 * The policies are components of the same company definition, so a reference is
 * resolved against it and the card shows the real thing. A reference this
 * company does not declare is drawn as exactly that — a named policy that is
 * not here — and never as an empty policy.
 *
 * What a stage must produce before it may be left lives in the gate policy, not
 * on the stage, so it is drawn where the record puts it: one list, under the
 * policy that owns it, for the whole workflow.
 */
export function Rules({
  workflow,
  document,
}: {
  readonly workflow: WorkflowFact;
  readonly document: CompanyBundleDocument;
}): ReactElement {
  const gates = policyResource(document, "gate_policy", workflow.gatesRef);
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle>Contracts</CardTitle>
        </CardHeader>
        <CardBody className="space-y-1.5">
          <Line label="takes in" value={workflow.inputContract} />
          <Line label="ends at" value={workflow.terminalContract} />
        </CardBody>
      </Card>

      <PolicyCard
        title="Gates"
        kind="gate_policy"
        reference={workflow.gatesRef}
        document={document}
      >
        {gates === null ? null : <Criteria payload={gates.payload} />}
      </PolicyCard>

      <PolicyCard
        title="Execution"
        kind="execution_policy"
        reference={workflow.executionRef}
        document={document}
      >
        {null}
      </PolicyCard>
    </div>
  );
}

function PolicyCard({
  title,
  kind,
  reference,
  document,
  children,
}: {
  readonly title: string;
  readonly kind: ComponentKind;
  readonly reference: string | null;
  readonly document: CompanyBundleDocument;
  readonly children: ReactElement | null;
}): ReactElement {
  const resource = policyResource(document, kind, reference);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <span className="flex-1" />
        {reference === null ? null : <Mono className="text-muted">{reference}</Mono>}
        {resource === null ? null : <StatusChip payload={resource.payload} />}
      </CardHeader>
      <CardBody className="space-y-1.5">
        {resource !== null ? <Declared resource={resource}>{children}</Declared> : null}
        {resource === null ? <Absent title={title} named={reference !== null} /> : null}
      </CardBody>
    </Card>
  );
}

/** A policy this company does not carry, and which of the two reasons it is. */
function Absent({
  title,
  named,
}: {
  readonly title: string;
  readonly named: boolean;
}): ReactElement {
  return (
    <p className="m-0 text-sm text-muted">
      {named
        ? "This company does not declare it. Nothing here can say what it holds."
        : `This workflow names no ${title.toLowerCase()} policy.`}
    </p>
  );
}

function Declared({
  resource,
  children,
}: {
  readonly resource: CompanyBundleResource;
  readonly children: ReactElement | null;
}): ReactElement {
  const note = resource.payload.note;
  return (
    <>
      <Line label="revision" value={`r${String(resource.component.revision)}`} />
      <Line
        label="digest"
        value={shortDigest(resource.component.content_digest)}
        title={resource.component.content_digest}
      />
      {children}
      {typeof note === "string" && note.length > 0 ? (
        <p className="m-0 pt-1 text-sm text-muted">{note}</p>
      ) : null}
    </>
  );
}

/** The gate policy's own criteria: what a candidate has to satisfy to pass. */
function Criteria({
  payload,
}: {
  readonly payload: Readonly<Record<string, unknown>>;
}): ReactElement | null {
  const criteria = payload.criteria;
  if (!Array.isArray(criteria) || criteria.length === 0) {
    return null;
  }
  return (
    <div className="space-y-1.5 pt-2">
      <span className="text-2xs text-muted">must hold</span>
      {(criteria as readonly unknown[]).map((entry, index) => (
        <Criterion key={index} entry={entry} />
      ))}
    </div>
  );
}

function Criterion({ entry }: { readonly entry: unknown }): ReactElement | null {
  if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
    return null;
  }
  const held = entry as Readonly<Record<string, unknown>>;
  const key = held.key;
  const description = held.description;
  return (
    <div className="flex items-baseline gap-3 border-t border-line pt-1.5">
      <Mono className="w-40 shrink-0 text-muted">{typeof key === "string" ? key : "—"}</Mono>
      <span className="min-w-0 flex-1 text-sm text-fg">
        {typeof description === "string" ? description : ""}
      </span>
      {held.requires_verdict === true ? <Chip>needs a verdict</Chip> : null}
    </div>
  );
}

function StatusChip({
  payload,
}: {
  readonly payload: Readonly<Record<string, unknown>>;
}): ReactElement | null {
  const status = payload.status;
  return typeof status === "string" ? <Chip>{status}</Chip> : null;
}

function Line({
  label,
  value,
  title,
}: {
  readonly label: string;
  readonly value: string | null;
  readonly title?: string;
}): ReactElement {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-24 shrink-0 text-2xs text-muted">{label}</span>
      {value === null ? (
        <span className="text-sm text-muted">not declared</span>
      ) : (
        <Mono className="min-w-0 flex-1 truncate text-muted" title={title ?? value}>
          {value}
        </Mono>
      )}
    </div>
  );
}
