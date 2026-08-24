import { useState } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import type { ReactElement } from "react";
import { resourceOf } from "../mint/component";
import { canonicalDigest } from "../mint/digest";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Mono } from "../ui/primitives";
import { Field } from "../ui/form";
import { EntityRow } from "../wizard/compose/EntityRow";
import { agentFacts } from "../wizard/read";
import type { Authoring } from "../wizard/ceremony";
import { AUTHORED_HERE, choicesOf, Picker } from "./HarnessPage";

/**
 * Agents: the ones this company has, and one more.
 *
 * An agent is two authored components, the same two the first-run wizard
 * writes: the persona it speaks as and the profile that pairs that persona with
 * a harness. Both are minted here, both are checked and planned before anything
 * is recorded, and the harness is chosen from the ones this company already
 * runs on — a profile pointing at a harness that is not in the bundle would be
 * a claim about a runtime nobody declared.
 */
export function AgentsPanel({ authoring }: { readonly authoring: Authoring }): ReactElement {
  const harnesses = choicesOf(authoring.recorded, "harness");
  const [draft, setDraft] = useState<Draft>(() => ({
    ...BLANK,
    harness: harnesses[0]?.value ?? "",
  }));
  const facts = agentFacts(authoring.recorded);
  const ready =
    draft.name.trim().length > 0 && draft.key.trim().length > 2 && draft.harness.length > 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Agents</CardTitle>
          <span className="flex-1" />
          <Mono className="text-muted">{facts.length}</Mono>
        </CardHeader>
        <CardBody className="space-y-2">
          {facts.length === 0 ? (
            <p className="m-0 text-sm text-muted">
              No agent is in this company yet. Add the first one below.
            </p>
          ) : (
            facts.map((fact) => <EntityRow key={fact.id} fact={fact} subjectNoun="seat" />)
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Add an agent</CardTitle>
        </CardHeader>
        <CardBody className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Name" hint="What this agent is called wherever it speaks.">
              <Input
                value={draft.name}
                placeholder="Commander"
                onChange={(event): void => {
                  setDraft(named(draft, event.target.value));
                }}
              />
            </Field>
            <Field label="Key" hint="Lower-case letters, digits, dots and hyphens.">
              <Input
                className="font-mono"
                value={draft.key}
                placeholder="acme.commander"
                spellCheck={false}
                onChange={(event): void => {
                  setDraft({ ...draft, key: event.target.value });
                }}
              />
            </Field>
          </div>

          <Picker
            label="Harness"
            hint="The runtime this agent is created on."
            choices={harnesses}
            value={draft.harness}
            empty="This company runs on no harness yet, and an agent is created on one."
            onValue={(harness): void => {
              setDraft({ ...draft, harness });
            }}
          />
        </CardBody>
      </Card>

      <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
        <span className="flex-1" />
        <Button
          variant="primary"
          disabled={!ready}
          title={ready ? undefined : "Name the agent and pick a harness first."}
          onClick={(): void => {
            authoring.propose(withAgent(authoring, draft));
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
  /** `key@revision` of the harness this agent is created on. */
  readonly harness: string;
}

const BLANK: Draft = { name: "", key: "", harness: "" };

/** The key follows the name until the operator types their own. */
function named(draft: Draft, name: string): Draft {
  return { ...draft, name, key: draft.key === keyFor(draft.name) ? keyFor(name) : draft.key };
}

function keyFor(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

/** The recorded bundle with one authored agent in it, and nothing else moved. */
function withAgent(authoring: Authoring, draft: Draft): CompanyBundleDocument {
  const key = draft.key.trim();
  const name = draft.name.trim();
  const persona = {
    schema: "ctower.persona/v1",
    key,
    display_name: name,
    // The instructions this agent starts from are not written on this screen —
    // a persona document is the agent-files surface — so the digest is over the
    // one thing that was typed here. It is a real value over real input rather
    // than a pointer at text that does not exist.
    instructions_digest: canonicalDigest({ agent: name }),
  };
  const profile = {
    schema: "ctower.agent-profile/v1",
    key,
    persona_ref: `${key}@1`,
    harness_ref: draft.harness,
    skill_refs: [],
    tool_refs: [],
    execution: "not_exercised",
  };
  return {
    ...authoring.recorded,
    resources: [
      ...authoring.recorded.resources,
      resourceOf(
        {
          kind: "persona",
          schemaRef: "ctower.persona/v1",
          payload: persona,
          source: AUTHORED_HERE,
        },
        authoring.tenant
      ),
      resourceOf(
        {
          kind: "agent_profile",
          schemaRef: "ctower.agent-profile/v1",
          payload: profile,
          source: AUTHORED_HERE,
        },
        authoring.tenant
      ),
    ],
  };
}
