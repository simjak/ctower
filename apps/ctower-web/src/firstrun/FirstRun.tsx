import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { ask, commands, computations } from "../api/client";
import type { Answer } from "../api/client";
import { Button, Input } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { commandKeyFor } from "../wizard/apply/commandKey";
import { Malformed, Refused, Unreachable } from "../wizard/states";

/**
 * The first-run moment: thirty seconds, once.
 *
 * Two fields and one button. The full bundle editor is the Company page and is
 * deliberately not here — an operator standing in front of an empty tower is
 * answering "what is this company called", not authoring a catalog.
 *
 * The button runs the real ceremony end to end: check, plan, apply. It does not
 * pretend to succeed and it does not pre-judge the answer; whatever ctower says
 * is what the screen says.
 */
export function FirstRun({ onCreated }: { readonly onCreated: () => void }): ReactElement {
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [keyTouched, setKeyTouched] = useState(false);
  const [outcome, setOutcome] = useState<Answer<unknown> | null>(null);

  const sending = outcome?.kind === "asking";
  const ready = name.trim().length > 0 && key.trim().length > 0 && !sending;

  const create = (): void => {
    setOutcome({ kind: "asking" });
    void (async (): Promise<void> => {
      const answer = await createCompany(documentFor(key.trim(), name.trim()));
      setOutcome(answer);
      if (answer.kind === "answered") {
        onCreated();
      }
    })();
  };

  return (
    <div className="grid place-items-center bg-[radial-gradient(600px_200px_at_50%_0%,color-mix(in_srgb,var(--amber)_7%,transparent),transparent)] py-14">
      <div className="w-[min(420px,100%)] rounded-md border border-line bg-card p-7">
        <h1 className="m-0 text-lg font-bold tracking-[-0.02em]">Create your company</h1>
        <p className="mt-1 mb-4 text-sm text-muted">
          One company per tower. Everything else lives inside it.
        </p>

        <label className="mt-3 mb-1 block text-xs text-muted" htmlFor="company-name">
          Name
        </label>
        <Input
          id="company-name"
          value={name}
          placeholder="Jakit Labs"
          onChange={(event): void => {
            setName(event.target.value);
            if (!keyTouched) {
              setKey(slug(event.target.value));
            }
          }}
        />

        <label className="mt-3 mb-1 block text-xs text-muted" htmlFor="company-key">
          Key
        </label>
        <Input
          id="company-key"
          className="font-mono text-sm"
          value={key}
          placeholder="jakit-labs"
          spellCheck={false}
          onChange={(event): void => {
            setKeyTouched(true);
            setKey(event.target.value);
          }}
        />

        <Button variant="primary" className="mt-5 w-full" disabled={!ready} onClick={create}>
          {sending ? (
            <>
              <Mark name="working" /> Creating
            </>
          ) : (
            <>Create company →</>
          )}
        </Button>

        {outcome === null || outcome.kind === "asking" || outcome.kind === "answered" ? null : (
          <div className="mt-4">
            <Outcome answer={outcome} />
          </div>
        )}
      </div>
    </div>
  );
}

function Outcome({ answer }: { readonly answer: Answer<unknown> }): ReactElement | null {
  switch (answer.kind) {
    case "refused":
      return (
        <Refused
          problem={answer.problem}
          action="A company needs at least one authored component. Install a component pack with ctowerctl, then create."
        />
      );
    case "unreachable":
      return <Unreachable detail={answer.detail} action="Nothing was created. Try again." />;
    case "malformed":
      return <Malformed detail={answer.detail} />;
    case "asking":
    case "answered":
      return null;
  }
}

/**
 * Check, plan, apply — in that order, stopping at the first thing that is not
 * an answer. The plan's digest and base version are what apply is sent, so the
 * command can only ever apply the plan that was actually computed.
 */
async function createCompany(bundle: CompanyBundleDocument): Promise<Answer<unknown>> {
  const checked = await ask(() => computations.validateCompanyBundle({ body: { bundle } }));
  if (checked.kind !== "answered") {
    return checked;
  }
  const planned = await ask(() => computations.planCompanyBundle({ body: { bundle } }));
  if (planned.kind !== "answered") {
    return planned;
  }
  return ask(() =>
    commands.applyCompanyBundle({
      IdempotencyKey: commandKeyFor(planned.value.plan_digest),
      body: {
        bundle,
        expected_active_version: planned.value.base_version,
        plan_digest: planned.value.plan_digest,
      },
    })
  );
}

function documentFor(key: string, displayName: string): CompanyBundleDocument {
  return {
    schema: "ctower.company-bundle/v1",
    company: { key, display_name: displayName },
    resources: [],
    assignments: [],
    secret_binding_refs: [],
  };
}

/** A suggested key, until the operator types their own. */
function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}
