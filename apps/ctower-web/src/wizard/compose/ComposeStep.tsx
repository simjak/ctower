import type { ReactElement, ReactNode } from "react";
import {
  Badge,
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
import { agentFacts, componentCounts, projectFacts } from "../read";
import type { EntityFact } from "../read";
import type { Seed } from "../useSeed";
import { EntityRow } from "./EntityRow";

/**
 * Step 1 — company details.
 *
 * Three questions, in the order an operator asks them: what is this company
 * called, what does it deliver, and who works on it. Everything on this screen
 * is a fact the API returned; the two things the operator authors here are the
 * company's name and key, and which projects and agents are in.
 */
export function ComposeStep({
  seed,
  draft,
  onDraft,
}: {
  readonly seed: Seed;
  readonly draft: Draft;
  readonly onDraft: (draft: Draft) => void;
}): ReactElement {
  const projects = projectFacts(draft.base);
  const agents = agentFacts(draft.base);
  const keep = (id: string, kept: boolean): void => {
    const dropped = new Set(draft.dropped);
    if (kept) {
      dropped.delete(id);
    } else {
      dropped.add(id);
    }
    onDraft({ ...draft, dropped });
  };

  return (
    <>
      <PageHead title="Company details" subtitle={<Provenance seed={seed} />} />

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
          facts={projects}
          dropped={draft.dropped}
          subjectNoun="bindings"
          empty="No project is in this company yet."
          onKeep={keep}
        />

        <EntityCard
          title="Agents"
          facts={agents}
          dropped={draft.dropped}
          subjectNoun="seats"
          empty="No agent is in this company yet."
          onKeep={keep}
        />

        <Card>
          <CardHeader>
            <CardTitle>Everything else</CardTitle>
            <span className="flex-1" />
            <Badge tone="neutral">read only</Badge>
          </CardHeader>
          <CardBody className="flex flex-wrap gap-1.5">
            {componentCounts(draft.base).map((entry) => (
              <Badge key={entry.kind} tone="neutral">
                {entry.kind}
                <Mono className="text-ink-3">{entry.count}</Mono>
              </Badge>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Secrets</CardTitle>
            <span className="flex-1" />
            <Badge tone="info">references only</Badge>
          </CardHeader>
          <CardBody className="flex flex-wrap gap-1.5">
            {draft.base.secret_binding_refs.length === 0 ? (
              <p className="m-0 text-sm text-ink-3">No secret is bound to this company.</p>
            ) : (
              draft.base.secret_binding_refs.map((reference) => (
                <Badge key={reference.name} tone="neutral" title={reference.reference_class}>
                  <Mono>{reference.name}</Mono>
                </Badge>
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
  dropped,
  subjectNoun,
  empty,
  onKeep,
}: {
  readonly title: string;
  readonly facts: readonly EntityFact[];
  readonly dropped: ReadonlySet<string>;
  readonly subjectNoun: string;
  readonly empty: string;
  readonly onKeep: (id: string, kept: boolean) => void;
}): ReactElement {
  const kept = facts.filter((fact) => !dropped.has(fact.id)).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <span className="flex-1" />
        <Mono className="text-ink-3">
          {kept} of {facts.length}
        </Mono>
      </CardHeader>
      <CardBody className="space-y-2">
        {facts.length === 0 ? (
          <p className="m-0 text-sm text-ink-3">{empty}</p>
        ) : (
          facts.map((fact) => (
            <EntityRow
              key={fact.id}
              fact={fact}
              kept={!dropped.has(fact.id)}
              subjectNoun={subjectNoun}
              onKeep={(next): void => {
                onKeep(fact.id, next);
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
    return <Badge tone="unknown">new company</Badge>;
  }
  return (
    <>
      <Badge tone="proven" title={`Activated ${seed.result.metadata.activated_at}`}>
        version {seed.result.active_version}
      </Badge>
      <Mono className="text-ink-4" title={seed.result.bundle_digest}>
        {shortDigest(seed.result.bundle_digest)}
      </Mono>
    </>
  );
}
