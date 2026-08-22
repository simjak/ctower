import type { ChangeEvent, ReactElement } from "react";
import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { Checkbox, Field } from "../../ui/form";
import { Card, CardBody, CardHeader, CardTitle, Chip, Input, Mono } from "../../ui/primitives";
import { shortDigest } from "../../wizard/bundle";
import { withField } from "./compose";
import type { FileDraft } from "./compose";
import { capabilityChoices, dependentsOf, staleNamersOf, strings, text } from "./read";

/**
 * One agent file, open for editing.
 *
 * What is editable is what this browser can honestly author: the payload's own
 * fields, under the payload's own authored schema. What is not editable is not
 * greyed out and hinted at — it is stated. The instructions behind a persona or
 * a skill are one such thing: the payload pins them by digest and the authored
 * contract declares no operation that carries their bytes, so this screen shows
 * the pin and says where the text lives instead of offering a box that could
 * never be sent.
 */
export function FileEditor({
  document,
  draft,
  onDraft,
}: {
  readonly document: CompanyBundleDocument;
  readonly draft: FileDraft;
  readonly onDraft: (draft: FileDraft) => void;
}): ReactElement {
  const component = draft.base.component;
  const moves = dependentsOf(document, draft.base);
  const behind = staleNamersOf(document, draft.base);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{text(draft.payload, "display_name") ?? component.key}</CardTitle>
        <span className="flex-1" />
        <Mono className="text-muted">r{component.revision}</Mono>
        <Mono className="text-muted" title={component.content_digest}>
          {shortDigest(component.content_digest)}
        </Mono>
      </CardHeader>
      <CardBody className="space-y-5">
        <Field label="Name" hint="What people call this file on every screen and in every report.">
          <Input
            value={text(draft.payload, "display_name") ?? ""}
            onChange={(event: ChangeEvent<HTMLInputElement>): void => {
              onDraft(withField(draft, "display_name", event.target.value));
            }}
          />
        </Field>

        {component.kind === "tool" ? (
          <ToolCapability document={document} draft={draft} onDraft={onDraft} />
        ) : null}
        {component.kind === "skill" ? (
          <SkillCapabilities document={document} draft={draft} onDraft={onDraft} />
        ) : null}
        {component.kind === "tool" ? (
          <Field
            label="Authority"
            hint="The contract fixes this. Nothing on this screen grants it."
          >
            <div>
              <Chip title={text(draft.payload, "authority") ?? ""}>not granted</Chip>
            </div>
          </Field>
        ) : (
          <Field
            label="Instructions"
            hint="Pinned by digest. The text itself is in the pack this was authored from."
          >
            <Mono
              className="block truncate text-muted"
              title={text(draft.payload, "instructions_digest") ?? ""}
            >
              {shortDigest(text(draft.payload, "instructions_digest") ?? "")}
            </Mono>
          </Field>
        )}

        {moves.length === 0 && behind.length === 0 ? null : (
          <div className="space-y-1 border-t border-line pt-3">
            {moves.length === 0 ? null : (
              <Named what={moves} says="move with this edit, in the same command." />
            )}
            {behind.length === 0 ? null : (
              <Named what={behind} says="name an earlier revision and stay on it." />
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

/**
 * Who else this file is named by, and what happens to them.
 *
 * A component names this one in its declared pins, in its payload, or in both,
 * and the two can disagree. So the two answers are separate lines: what this
 * edit carries with it, and what is left on a revision it does not touch. The
 * second line is the one that explains an agent whose name did not change.
 */
function Named({
  what,
  says,
}: {
  readonly what: readonly CompanyBundleResource[];
  readonly says: string;
}): ReactElement {
  return (
    <p className="m-0 text-xs text-muted">
      {what.map((resource) => (
        <Mono key={resource.component.key} className="mr-2 text-muted">
          {resource.component.key}
        </Mono>
      ))}
      {says}
    </p>
  );
}

/**
 * A skill's capabilities. Only what this company declares is offered: a
 * capability the definition does not carry cannot be pinned to one exact
 * digest, and the registry refuses a bundle that names one.
 */
function SkillCapabilities({
  document,
  draft,
  onDraft,
}: {
  readonly document: CompanyBundleDocument;
  readonly draft: FileDraft;
  readonly onDraft: (draft: FileDraft) => void;
}): ReactElement {
  const held = strings(draft.payload, "capability_refs");
  return (
    <Field label="What it may use" hint="Only capabilities this company declares can be pinned.">
      <div className="space-y-2">
        {capabilityChoices(document).map((choice) => (
          <div key={choice.ref} className="flex items-center gap-2 text-sm">
            <Checkbox
              label={choice.name}
              checked={held.includes(choice.ref)}
              onCheckedChange={(checked): void => {
                onDraft(
                  withField(
                    draft,
                    "capability_refs",
                    checked
                      ? [...held, choice.ref].toSorted((left, right) => left.localeCompare(right))
                      : held.filter((reference) => reference !== choice.ref)
                  )
                );
              }}
            />
            <span>{choice.name}</span>
            <Mono className="text-muted">{choice.ref}</Mono>
          </div>
        ))}
      </div>
    </Field>
  );
}

/** A tool names exactly one capability, by key, and the record says which. */
function ToolCapability({
  document,
  draft,
  onDraft,
}: {
  readonly document: CompanyBundleDocument;
  readonly draft: FileDraft;
  readonly onDraft: (draft: FileDraft) => void;
}): ReactElement {
  return (
    <Field label="What it may use" hint="Only capabilities this company declares can be pinned.">
      <select
        className={[
          "h-9 w-full min-w-0 rounded-sm border border-line bg-bg px-3 text-sm text-fg",
          "focus:border-transparent focus:outline-2 focus:outline-offset-0 focus:outline-amber",
        ].join(" ")}
        value={text(draft.payload, "capability") ?? ""}
        onChange={(event: ChangeEvent<HTMLSelectElement>): void => {
          onDraft(withField(draft, "capability", event.target.value));
        }}
      >
        {capabilityChoices(document).map((choice) => (
          <option key={choice.key} value={choice.key}>
            {choice.name}
          </option>
        ))}
      </select>
    </Field>
  );
}
