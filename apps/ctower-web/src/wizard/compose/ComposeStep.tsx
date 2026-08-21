import type { ReactElement, ReactNode } from "react";
import {
  Chip,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Input,
  Mono,
  PageHead,
} from "../../ui/primitives";
import { Field } from "../../ui/form";
import { shortDigest } from "../bundle";
import type { Draft } from "../bundle";
import { PURPOSE } from "../mode";
import { agentFacts, componentCounts, projectFacts } from "../read";
import type { EntityFact } from "../read";
import type { Seed } from "../useSeed";
import { EntityRow } from "./EntityRow";

/**
 * Step 1 — what this company is.
 *
 * The title says which of the two things the operator is doing, because a
 * tenant that already has a company is not creating one. The one line under it
 * says what the screen is for, and there is no second line: the rest of the
 * screen is facts.
 */
export function ComposeStep({
  seed,
  draft,
  onDraft,
  title,
}: {
  readonly seed: Seed;
  readonly draft: Draft;
  readonly onDraft: (draft: Draft) => void;
  readonly title: string;
}): ReactElement {
  const setRemoved = (id: string, removed: boolean): void => {
    const next = new Set(draft.removed);
    if (removed) {
      next.add(id);
    } else {
      next.delete(id);
    }
    onDraft({ ...draft, removed: next });
  };

  return (
    <>
      <PageHead title={title} subtitle={PURPOSE}>
        <Provenance seed={seed} />
      </PageHead>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Identity</CardTitle>
          </CardHeader>
          <CardBody className="grid gap-5 sm:grid-cols-2">
            <Field
              label="Name"
              hint="What people call this company on every screen and in every report."
            >
              <Input
                value={draft.displayName}
                placeholder="Acme Robotics"
                onChange={(event): void => {
                  onDraft({ ...draft, displayName: event.target.value });
                }}
              />
            </Field>
            <Field
              label="Key"
              hint="Lower-case letters, digits and hyphens. It is what the record is keyed by."
            >
              <Input
                className="font-mono"
                value={draft.companyKey}
                placeholder="acme-robotics"
                spellCheck={false}
                onChange={(event): void => {
                  onDraft({ ...draft, companyKey: event.target.value });
                }}
              />
            </Field>
          </CardBody>
        </Card>

        <EntityCard
          title="Projects"
          facts={projectFacts(draft.base)}
          removed={draft.removed}
          subjectNoun="bindings"
          empty="No project is in this company yet."
          onRemove={setRemoved}
        />

        <EntityCard
          title="Agents"
          facts={agentFacts(draft.base)}
          removed={draft.removed}
          subjectNoun="seats"
          empty="No agent is in this company yet."
          onRemove={setRemoved}
        />

        <Card>
          <CardHeader>
            <CardTitle>Everything else</CardTitle>
            <span className="flex-1" />
            <Chip tone="neutral">read only</Chip>
          </CardHeader>
          <CardBody className="flex flex-wrap gap-1.5">
            {componentCounts(draft.base).map((entry) => (
              <Chip key={entry.kind} tone="neutral">
                {entry.kind}
                <Mono className="text-muted">{entry.count}</Mono>
              </Chip>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Secrets</CardTitle>
            <span className="flex-1" />
            <Chip tone="neutral">references only</Chip>
          </CardHeader>
          <CardBody className="flex flex-wrap gap-1.5">
            {draft.base.secret_binding_refs.length === 0 ? (
              <p className="m-0 text-sm text-muted">No secret is bound to this company.</p>
            ) : (
              draft.base.secret_binding_refs.map((reference) => (
                <Chip key={reference.name} tone="neutral" title={reference.reference_class}>
                  <Mono>{reference.name}</Mono>
                </Chip>
              ))
            )}
          </CardBody>
        </Card>
      </div>
    </>
  );
}

function EntityCard({
  title,
  facts,
  removed,
  subjectNoun,
  empty,
  onRemove,
}: {
  readonly title: string;
  readonly facts: readonly EntityFact[];
  readonly removed: ReadonlySet<string>;
  readonly subjectNoun: string;
  readonly empty: string;
  readonly onRemove: (id: string, removed: boolean) => void;
}): ReactElement {
  const retiring = facts.filter((fact) => removed.has(fact.id)).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <span className="flex-1" />
        {retiring === 0 ? null : <Chip tone="amber">{retiring} retiring</Chip>}
        <Mono className="text-muted">{facts.length - retiring} kept</Mono>
      </CardHeader>
      <CardBody className="space-y-2">
        {facts.length === 0 ? (
          <p className="m-0 text-sm text-muted">{empty}</p>
        ) : (
          facts.map((fact) => (
            <EntityRow
              key={fact.id}
              fact={fact}
              removed={removed.has(fact.id)}
              subjectNoun={subjectNoun}
              onRemove={(next): void => {
                onRemove(fact.id, next);
              }}
            />
          ))
        )}
      </CardBody>
    </Card>
  );
}

function Provenance({ seed }: { readonly seed: Seed }): ReactNode {
  if (seed.kind === "template") {
    return <Chip tone="neutral">new company</Chip>;
  }
  return (
    <>
      <Chip tone="ok" title={`Activated ${seed.result.metadata.activated_at}`}>
        version {seed.result.active_version}
      </Chip>
      <Mono className="text-muted" title={seed.result.bundle_digest}>
        {shortDigest(seed.result.bundle_digest)}
      </Mono>
    </>
  );
}
