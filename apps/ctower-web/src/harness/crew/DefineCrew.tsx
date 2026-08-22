import type { ReactElement } from "react";
import { Card, CardBody, CardHeader, CardTitle, Input, Mono } from "../../ui/primitives";
import { Field } from "../../ui/form";
import type { ProfileOption } from "./binding";
import { SCOPES, seatOf } from "./draft";
import type { CrewDraft } from "./draft";
import { ScopeChoice, Select } from "./fields";

/**
 * One form, and it is deliberately two halves.
 *
 * Who the crew is and where it works are two different records in ctower, and
 * pretending otherwise would hide the thing an operator most needs to know when
 * one of them refuses. So the screen names both halves and asks for them once.
 *
 * The credential is a reference and a fingerprint. There is no field for a
 * secret because there is no place for one: `SeatCredentialIssueRequest` carries
 * neither, the record stores neither, and this browser is not where a credential
 * should ever be typed.
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
  readonly projects: readonly string[];
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
              disabled={profiles.length === 0}
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
  readonly projects: readonly string[];
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>The address</CardTitle>
        <span className="flex-1" />
        <Mono className="text-muted">
          {draft.projectKey} / {seatOf(draft) === "" ? "…" : seatOf(draft)}
        </Mono>
      </CardHeader>
      <CardBody className="grid gap-5 sm:grid-cols-2">
        <Field label="Project" hint="The project's own key, which is not its document key.">
          <Select
            value={draft.projectKey}
            disabled={projects.length === 0}
            options={projects.map((key) => ({ value: key, label: key }))}
            onChange={(event): void => {
              onDraft({ ...draft, projectKey: event.target.value });
            }}
          />
        </Field>
        <Field label="Seat" hint="The address's own name. It need not match the crew's.">
          <Input
            className="font-mono"
            value={draft.seatKey}
            placeholder={draft.name === "" ? "engineer-3" : draft.name}
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
        <Field label="Credential reference" hint="Where the credential lives. ctower stores this.">
          <Input
            className="font-mono"
            value={draft.credentialRef}
            placeholder="secret-service:acme/seat/engineer-3"
            spellCheck={false}
            onChange={(event): void => {
              onDraft({ ...draft, credentialRef: event.target.value });
            }}
          />
        </Field>
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
