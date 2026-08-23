import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { resourceOf } from "../mint/component";
import { cn } from "../ui/cn";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Mono } from "../ui/primitives";
import { Field } from "../ui/form";
import { EntityRow } from "../wizard/compose/EntityRow";
import { projectFacts } from "../wizard/read";
import { AUTHORED_HERE, choicesOf, Picker } from "./HarnessPage";
import type { Authoring } from "./HarnessPage";

/**
 * Projects: the ones this company has, and one more.
 *
 * There is no `createProject` operation and there is not meant to be one. A
 * project is a component of the company bundle, so creating one is authoring a
 * `ctower.project/v1` document into the recorded bundle and handing the result
 * to the same check-plan-apply the wizard runs. Every field below is a field
 * that contract requires — including the goal, which is why it is chosen from
 * the goals the company already has rather than typed.
 */
export function ProjectsPanel({
  authoring,
  current,
}: {
  readonly authoring: Authoring;
  /** The project the rail's switcher is pointed at, marked in the list below. */
  readonly current: string | null;
}): ReactElement {
  const goals = choicesOf(authoring.recorded, "goal");
  const [draft, setDraft] = useState<Draft>(() => ({
    ...BLANK,
    goal: goals[0]?.value ?? "",
  }));
  const facts = projectFacts(authoring.recorded);
  const ready =
    draft.name.trim().length > 0 &&
    draft.key.trim().length > 2 &&
    draft.prefix.trim().length > 1 &&
    draft.repository.trim().length > 0 &&
    draft.goal.length > 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Projects</CardTitle>
          <span className="flex-1" />
          <Mono className="text-muted">{facts.length}</Mono>
        </CardHeader>
        <CardBody className="space-y-2">
          {facts.length === 0 ? (
            <p className="m-0 text-sm text-muted">
              No project is in this company yet. Add the first one below.
            </p>
          ) : (
            facts.map((fact) => (
              // The one the rail is pointed at wears the rail's own amber edge,
              // so switching in the sidebar is visible where the projects are.
              <div
                key={fact.id}
                aria-current={fact.key === current ? "true" : undefined}
                className={cn("rounded-md", fact.key === current ? "ring-1 ring-amber" : null)}
              >
                <EntityRow fact={fact} subjectNoun="binding" />
                {fact.key === current ? <span className="sr-only">current project</span> : null}
              </div>
            ))
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Add a project</CardTitle>
        </CardHeader>
        <CardBody className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Name" hint="What people call this project on every screen.">
              <Input
                value={draft.name}
                placeholder="Acme widgets"
                onChange={(event): void => {
                  setDraft(named(draft, event.target.value));
                }}
              />
            </Field>
            <Field label="Key" hint="Lower-case letters, digits, dots and hyphens.">
              <Input
                className="font-mono"
                value={draft.key}
                placeholder="acme-widgets"
                spellCheck={false}
                onChange={(event): void => {
                  setDraft({ ...draft, key: event.target.value });
                }}
              />
            </Field>
            <Field label="Ticket prefix" hint="Two to five capitals; it prefixes every ticket.">
              <Input
                className="font-mono"
                value={draft.prefix}
                placeholder="ACW"
                spellCheck={false}
                onChange={(event): void => {
                  setDraft({ ...draft, prefix: event.target.value.toUpperCase() });
                }}
              />
            </Field>
            <Field label="Repository" hint="The exact reference, host and path.">
              <Input
                className="font-mono"
                value={draft.repository}
                placeholder="repository:github/acme/widgets"
                spellCheck={false}
                onChange={(event): void => {
                  setDraft({ ...draft, repository: event.target.value });
                }}
              />
            </Field>
          </div>

          <Picker
            label="Goal"
            hint="The outcome this project serves. A project must name one."
            choices={goals}
            value={draft.goal}
            empty="This company has no goal yet, and a project must name one."
            onValue={(goal): void => {
              setDraft({ ...draft, goal });
            }}
          />
        </CardBody>
      </Card>

      <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
        <span className="flex-1" />
        <Button
          variant="primary"
          disabled={!ready}
          title={ready ? undefined : "Fill every field above first."}
          onClick={(): void => {
            authoring.propose(withProject(authoring, draft));
          }}
        >
          Review changes →
        </Button>
      </footer>
    </div>
  );
}

interface Draft {
  readonly name: string;
  readonly key: string;
  readonly prefix: string;
  readonly repository: string;
  /** `key@revision` of the goal this project serves. */
  readonly goal: string;
}

const BLANK: Draft = { name: "", key: "", prefix: "", repository: "", goal: "" };

/**
 * The key and the prefix follow the name until the operator types their own,
 * and then they stop following it. Both are things the record is keyed by, so
 * neither may quietly change under an operator who has set it deliberately.
 */
function named(draft: Draft, name: string): Draft {
  return {
    ...draft,
    name,
    key: draft.key === keyFor(draft.name) ? keyFor(name) : draft.key,
    prefix: draft.prefix === prefixFor(draft.name) ? prefixFor(name) : draft.prefix,
  };
}

function keyFor(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

function prefixFor(name: string): string {
  return name
    .toUpperCase()
    .replace(/[^A-Z]/g, "")
    .slice(0, 3);
}

/** The recorded bundle with one authored project in it, and nothing else moved. */
function withProject(authoring: Authoring, draft: Draft): CompanyBundleDocument {
  const payload = {
    schema: "ctower.project/v1",
    key: draft.key.trim(),
    display_name: draft.name.trim(),
    prefix: draft.prefix.trim(),
    repository_ref: draft.repository.trim(),
    goal_refs: [draft.goal],
  };
  const resource = resourceOf(
    { kind: "project", schemaRef: "ctower.project/v1", payload, source: AUTHORED_HERE },
    authoring.tenant
  );
  return {
    ...authoring.recorded,
    resources: [...authoring.recorded.resources, resource],
  };
}
