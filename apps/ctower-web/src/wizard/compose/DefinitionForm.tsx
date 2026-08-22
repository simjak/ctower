import type { ReactElement } from "react";
import { Card, CardBody, CardHeader, CardTitle, Mono } from "../../ui/primitives";
import { Field } from "../../ui/form";
import { Input } from "../../ui/primitives";
import type { Draft } from "../bundle";
import { agentFacts, projectFacts } from "../read";
import type { EntityFact } from "../read";
import { EntityRow } from "./EntityRow";

/**
 * What this company is: its name and key, its projects, and its agents.
 *
 * The projects and the agents are shown and not edited. The registry answers
 * `bundle-compatibility-refused` to any plan that deprecates a component, so a
 * removal here could only ever build a document that apply would reject; the
 * control says so where it sits rather than letting the operator find out at
 * the end of a review.
 *
 * The component inventory and the secret bindings used to sit under these and
 * are gone. Neither is something an operator does anything with here — one is a
 * count of things this screen cannot author, the other a list it cannot change
 * — and a section that only reports is a section that belongs on a page whose
 * job is reporting.
 */
export function DefinitionForm({
  draft,
  onDraft,
}: {
  readonly draft: Draft;
  readonly onDraft: (draft: Draft) => void;
}): ReactElement {
  return (
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
        subjectNoun="binding"
        empty="No project is in this company yet."
      />

      <EntityCard
        title="Agents"
        facts={agentFacts(draft.base)}
        subjectNoun="seat"
        empty="No agent is in this company yet."
      />
    </div>
  );
}

function EntityCard({
  title,
  facts,
  subjectNoun,
  empty,
}: {
  readonly title: string;
  readonly facts: readonly EntityFact[];
  readonly subjectNoun: string;
  readonly empty: string;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <span className="flex-1" />
        <Mono className="text-muted">{facts.length}</Mono>
      </CardHeader>
      <CardBody className="space-y-2">
        {facts.length === 0 ? (
          <p className="m-0 text-sm text-muted">{empty}</p>
        ) : (
          facts.map((fact) => <EntityRow key={fact.id} fact={fact} subjectNoun={subjectNoun} />)
        )}
      </CardBody>
    </Card>
  );
}
