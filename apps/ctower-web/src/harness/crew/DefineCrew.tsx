import type { ReactElement } from "react";
import { Card, CardBody, CardHeader, CardTitle, Input, Mono } from "../../ui/primitives";
import { Field } from "../../ui/form";
import type { ProfileOption } from "./binding";
import { REFERENCE_CLASSES, SCOPES } from "./draft";
import type { CrewDraft } from "./draft";
import { ScopeChoice, Select } from "./fields";
import type { ProjectOption } from "./roster";

/**
 * One form, and it is deliberately two halves.
 *
 * Who the crew is and where it works are two different records in ctower, and
 * pretending otherwise would hide the thing an operator most needs to know when
 * one of them refuses. So the screen names both halves and asks for them once.
 *
 * The credential is a reference and a fingerprint. There is no field a secret
 * would fit in: the class comes from the contract's own closed set, the rest has
 * to be shaped like a path, and a credential value is neither. `credential_ref`
 * on the wire would take one — that is what makes composing it here the job of
 * the screen rather than a note in the hint.
 */
export function DefineCrew({
  draft,
  onDraft,
  prefix,
  profiles,
  projects,
}: {
  readonly draft: CrewDraft;
  readonly onDraft: (draft: CrewDraft) => void;
  readonly prefix: string;
  readonly profiles: readonly ProfileOption[];
  readonly projects: readonly ProjectOption[];
}): ReactElement {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>The crew</CardTitle>
          <span className="flex-1" />
          <Mono className="text-muted">
            {prefix}:{draft.name === "" ? "…" : draft.name}
          </Mono>
        </CardHeader>
        <CardBody className="grid gap-5 sm:grid-cols-2">
          <Field label="Name" hint="What the company record calls this crew.">
            <div className="flex items-center gap-2">
              <Mono className="shrink-0 text-muted">{prefix}:</Mono>
              <Input
                className="font-mono"
                value={draft.name}
                placeholder="engineer-3"
                spellCheck={false}
                onChange={(event): void => {
                  onDraft({ ...draft, name: event.target.value });
                }}
              />
            </div>
          </Field>
          <Field label="Profile" hint="The agent profile this crew runs. It must already exist.">
            <Select
              value={draft.profileKey}
              empty="No agent profile is recorded"
              options={profiles.map((profile) => ({ value: profile.key, label: profile.key }))}
              onChange={(event): void => {
                onDraft({ ...draft, profileKey: event.target.value });
              }}
            />
          </Field>
        </CardBody>
      </Card>

      <AddressHalf draft={draft} onDraft={onDraft} projects={projects} />
    </div>
  );
}

function AddressHalf({
  draft,
  onDraft,
  projects,
}: {
  readonly draft: CrewDraft;
  readonly onDraft: (draft: CrewDraft) => void;
  readonly projects: readonly ProjectOption[];
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>The address</CardTitle>
        <span className="flex-1" />
        <Mono className="text-muted">
          {draft.projectKey === "" ? "…" : draft.projectKey} /{" "}
          {draft.seatKey === "" ? "…" : draft.seatKey}
        </Mono>
      </CardHeader>
      <CardBody className="grid gap-5 sm:grid-cols-2">
        <Field label="Project" hint="The project this crew works in, as the record names it.">
          <Select
            value={draft.projectKey}
            empty="This company records no project"
            options={projects.map((project) => ({
              value: project.key,
              label: project.addressable ? project.key : `${project.key} — no address possible`,
              unavailable: !project.addressable,
            }))}
            onChange={(event): void => {
              onDraft({ ...draft, projectKey: event.target.value });
            }}
          />
        </Field>
        <Field label="Seat" hint="The seat this address is for. It is never taken from a name.">
          <Input
            className="font-mono"
            value={draft.seatKey}
            placeholder="engineer-3"
            spellCheck={false}
            onChange={(event): void => {
              onDraft({ ...draft, seatKey: event.target.value });
            }}
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Can do" hint="What a bearer of this address is allowed to record.">
            <ScopeChoice
              all={SCOPES}
              chosen={draft.scopes}
              onChosen={(scopes): void => {
                onDraft({ ...draft, scopes });
              }}
            />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field
            label="Where the credential lives"
            hint="The place, never the credential. A path, in one of the classes ctower knows."
          >
            <div className="flex min-w-0 items-center gap-2">
              <Select
                className="w-44 shrink-0"
                value={draft.refClass}
                empty=""
                options={REFERENCE_CLASSES.map((held) => ({ value: held, label: held }))}
                onChange={(event): void => {
                  onDraft({ ...draft, refClass: classOf(event.target.value, draft.refClass) });
                }}
              />
              <Input
                className="font-mono"
                value={draft.refLocator}
                placeholder="acme/seat/engineer-3"
                spellCheck={false}
                onChange={(event): void => {
                  onDraft({ ...draft, refLocator: event.target.value });
                }}
              />
            </div>
          </Field>
        </div>
        <Field label="Fingerprint" hint="The credential's sha256, published by whoever holds it.">
          <Input
            className="font-mono"
            value={draft.fingerprint}
            placeholder="sha256:…"
            spellCheck={false}
            onChange={(event): void => {
              onDraft({ ...draft, fingerprint: event.target.value });
            }}
          />
        </Field>
      </CardBody>
    </Card>
  );
}

/** A class is one of the contract's own, or the draft keeps the one it had. */
function classOf(chosen: string, held: CrewDraft["refClass"]): CrewDraft["refClass"] {
  return REFERENCE_CLASSES.find((known) => known === chosen) ?? held;
}
