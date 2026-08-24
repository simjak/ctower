import type { ChangeEvent, ReactElement } from "react";
import type { CompanyBundleDocument, CompanyBundleResource } from "@ctower/client";
import { Checkbox, Field } from "../../ui/form";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Chip,
  Input,
  Select,
} from "../../ui/primitives";
import { Advanced } from "./Advanced";
import { withField } from "./compose";
import type { FileDraft } from "./compose";
import { capabilityChoices, dependentsOf, nameOf, staleNamersOf, strings, text } from "./read";
import { knownAs } from "./agent";

/**
 * One thing this agent reads, open for editing.
 *
 * What is editable is what this browser can honestly author: the payload's own
 * fields, under the payload's own authored schema. What is not editable is not
 * greyed out and hinted at — it is stated.
 *
 * The instruction text is the largest such thing, and it is worth saying plainly
 * because the reference console this screen was drawn from has a markdown editor
 * here. ctower's record does not. `persona.schema.json` and `skill.schema.json`
 * close their payloads with `additionalProperties: false` and carry
 * `instructions_digest` — a pin over the bytes, not the bytes — so there is no
 * field for prose to be written into and no operation that would carry it. A
 * text area here could never be sent, and a Save that cannot save is the one
 * thing an honest surface must not draw.
 *
 * The header carries no revision and no digest any more. Both moved into
 * `Advanced`, which is where AC-7 puts machine text and where the operator's own
 * amendment puts Mode, Root and Entry — one disclosure, one audience.
 */
export function FileEditor({
  document,
  draft,
  onDraft,
  edited,
  onReview,
}: {
  readonly document: CompanyBundleDocument;
  readonly draft: FileDraft;
  readonly onDraft: (draft: FileDraft) => void;
  /** Whether the payload differs from what is recorded, asked by digest. */
  readonly edited: boolean;
  readonly onReview: () => void;
}): ReactElement {
  const component = draft.base.component;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{nameOf(draft.base)}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-5">
        <Field label="Name" hint="What people call this on every screen and in every report.">
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
              <Chip>not granted</Chip>
            </div>
          </Field>
        ) : (
          <Field
            label="Instructions"
            hint="ctower records a fingerprint of this text, never the text. It is edited in the pack this was authored from."
          >
            <p className="m-0 text-sm text-muted">Kept outside this console.</p>
          </Field>
        )}

        <Moves document={document} resource={draft.base} />
        <Advanced component={component} />

        {edited ? (
          <footer className="flex items-center gap-2 border-t border-line pt-4">
            <span className="flex-1" />
            <Button variant="primary" onClick={onReview}>
              Review changes →
            </Button>
          </footer>
        ) : null}
      </CardBody>
    </Card>
  );
}

/**
 * Who else is named by this file, and what happens to each of them.
 *
 * A dependency pin is exact, so a new revision of a file is a new revision of
 * everything that names it — and anything left on an earlier revision does not
 * move, which is exactly what "my edit did nothing" looks like from the outside.
 * Both answers are said in names, not in keys: the operator recognises the
 * agent, and the record's addressing is the wiring's business.
 */
function Moves({
  document,
  resource,
}: {
  readonly document: CompanyBundleDocument;
  readonly resource: CompanyBundleResource;
}): ReactElement | null {
  const moves = dependentsOf(document, resource);
  const behind = staleNamersOf(document, resource);
  if (moves.length === 0 && behind.length === 0) {
    return null;
  }
  return (
    <div className="space-y-1 border-t border-line pt-3">
      {moves.length === 0 ? null : (
        <Named document={document} what={moves} says="Changes with this edit" />
      )}
      {behind.length === 0 ? null : (
        <Named document={document} what={behind} says="Stays on the older version" />
      )}
    </div>
  );
}

/**
 * Said in names, never in keys. `knownAs` is what resolves them, because an
 * agent profile carries no name of its own and the component key it would
 * otherwise fall back to is machine text in the operator's face.
 */
function Named({
  document,
  what,
  says,
}: {
  readonly document: CompanyBundleDocument;
  readonly what: readonly CompanyBundleResource[];
  readonly says: string;
}): ReactElement {
  return (
    <p className="m-0 text-xs text-muted">
      {says}: {what.map((resource) => knownAs(document, resource)).join(" · ")}
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
    <Field label="What it may use" hint="Only what this company declares can be pinned.">
      <div className="space-y-2">
        {capabilityChoices(document).map((choice) => (
          <div key={choice.ref} className="flex items-center gap-2 text-sm">
            <Checkbox
              label={choice.name}
              checked={held.includes(choice.ref)}
              onCheckedChange={(checked): void => {
                onDraft(withField(draft, "capability_refs", chosen(held, choice.ref, checked)));
              }}
            />
            <span>{choice.name}</span>
          </div>
        ))}
      </div>
    </Field>
  );
}

function chosen(held: readonly string[], ref: string, checked: boolean): readonly string[] {
  return checked
    ? [...held, ref].toSorted((left, right) => left.localeCompare(right))
    : held.filter((reference) => reference !== ref);
}

/** A tool names exactly one capability, and the record says which. */
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
    <Field label="What it may use" hint="Only what this company declares can be pinned.">
      <Select
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
      </Select>
    </Field>
  );
}
