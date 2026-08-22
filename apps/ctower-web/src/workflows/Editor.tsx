import type { ReactElement } from "react";
import type { CompanyBundleDocument, ComponentKind } from "@ctower/client";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Select } from "../ui/primitives";
import { Checkbox, Field } from "../ui/form";
import { cn } from "../ui/cn";
import { projectKeys } from "./compose";
import { STATUSES } from "./draft";
import type { WorkflowDraft } from "./draft";
import { RouteRows, StageRows, TransitionRows } from "./StageRows";

/**
 * Composing a workflow.
 *
 * Nothing here writes. The form holds a draft and the ceremony that follows is
 * the company bundle's own: check it, plan it, and let the operator read the
 * registry's answer before a command is sent. So the only way forward on this
 * screen is *Review changes*, and it appears when there is a change to review.
 *
 * Two fields are deliberately not editable and each says why where it sits. A
 * key is what the record is keyed by, so changing it does not revise a workflow
 * — it declares a different one, and the way to do that is to add one. And the
 * revision is the registry's to decide: this screen never claims a number the
 * record has not agreed to.
 */
export function Editor({
  draft,
  onDraft,
  document,
}: {
  readonly draft: WorkflowDraft;
  readonly onDraft: (draft: WorkflowDraft) => void;
  readonly document: CompanyBundleDocument;
}): ReactElement {
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle>Definition</CardTitle>
        </CardHeader>
        <CardBody className="grid gap-5 sm:grid-cols-2">
          <Field label="Key" hint="What the record keys this workflow by. It never changes.">
            <Input
              className="font-mono"
              disabled={draft.base !== null}
              placeholder="engineering.software-factory"
              spellCheck={false}
              value={draft.key}
              onChange={(event): void => {
                onDraft({ ...draft, key: event.target.value });
              }}
            />
          </Field>
          <Field label="Publication" hint="How far through publication this workflow has come.">
            <Select
              value={draft.status}
              onChange={(event): void => {
                onDraft({ ...draft, status: event.target.value });
              }}
            >
              {offered(STATUSES, draft.status).map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Takes in"
            hint="The shape of work this workflow accepts at the entry stage."
          >
            <Input
              className="font-mono"
              placeholder="software-change-ticket-v1"
              spellCheck={false}
              value={draft.inputContract}
              onChange={(event): void => {
                onDraft({ ...draft, inputContract: event.target.value });
              }}
            />
          </Field>
          <Field
            label="Ends at"
            hint="The shape of work this workflow leaves behind when it closes."
          >
            <Input
              className="font-mono"
              placeholder="verified-release-v1"
              spellCheck={false}
              value={draft.terminalContract}
              onChange={(event): void => {
                onDraft({ ...draft, terminalContract: event.target.value });
              }}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Note" hint="One line, for whoever reads this definition next.">
              <Input
                value={draft.note}
                placeholder="What this workflow is for."
                onChange={(event): void => {
                  onDraft({ ...draft, note: event.target.value });
                }}
              />
            </Field>
          </div>
        </CardBody>
      </Card>

      <StageRows draft={draft} onDraft={onDraft} />

      <Card>
        <CardHeader>
          <CardTitle>Entry stage</CardTitle>
        </CardHeader>
        <CardBody>
          <Select
            aria-label="Entry stage"
            className="max-w-xs font-mono"
            value={draft.initialStage}
            onChange={(event): void => {
              onDraft({ ...draft, initialStage: event.target.value });
            }}
          >
            <option value="">—</option>
            {offered(
              draft.stages.map((stage) => stage.key).filter((key) => key.length > 0),
              draft.initialStage
            ).map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </Select>
        </CardBody>
      </Card>

      <TransitionRows draft={draft} onDraft={onDraft} />
      <RouteRows draft={draft} onDraft={onDraft} />

      <Card>
        <CardHeader>
          <CardTitle>Policies</CardTitle>
        </CardHeader>
        <CardBody className="grid gap-5 sm:grid-cols-2">
          <PolicyField
            label="Gates"
            hint="What a candidate must satisfy before a stage may be left."
            example="engineering.software-factory.gates@1"
            kind="gate_policy"
            document={document}
            value={draft.gatesRef}
            onChange={(value): void => {
              onDraft({ ...draft, gatesRef: value });
            }}
          />
          <PolicyField
            label="Execution"
            hint="Which seats run each stage, and under which review plan."
            example="engineering.software-factory.execution@1"
            kind="execution_policy"
            document={document}
            value={draft.executionRef}
            onChange={(value): void => {
              onDraft({ ...draft, executionRef: value });
            }}
          />
        </CardBody>
      </Card>

      <Projects draft={draft} onDraft={onDraft} document={document} />
    </div>
  );
}

/**
 * A reference to a policy, offering the ones this company declares without
 * closing the set: the schema takes any `key@revision`, and a company may name
 * a policy it is about to add in the same change.
 */
function PolicyField({
  label,
  hint,
  example,
  kind,
  document,
  value,
  onChange,
}: {
  readonly label: string;
  readonly hint: string;
  readonly example: string;
  readonly kind: ComponentKind;
  readonly document: CompanyBundleDocument;
  readonly value: string;
  readonly onChange: (value: string) => void;
}): ReactElement {
  const listId = `declared-${kind}`;
  const declared = document.resources
    .filter((resource) => resource.component.kind === kind)
    .map((resource) => `${resource.component.key}@${String(resource.component.revision)}`);
  return (
    <Field label={label} hint={hint}>
      <Input
        className="font-mono"
        list={listId}
        placeholder={example}
        spellCheck={false}
        value={value}
        onChange={(event): void => {
          onChange(event.target.value);
        }}
      />
      <datalist id={listId}>
        {declared.map((reference) => (
          <option key={reference} value={reference} />
        ))}
      </datalist>
    </Field>
  );
}

/**
 * Which projects run this workflow.
 *
 * A binding names an exact revision, so revising a workflow rewrites every
 * binding that pointed at the one it replaces. That makes this list part of the
 * change and not a separate screen — and it is why an unticked project is a
 * project the new revision will not be bound to.
 */
function Projects({
  draft,
  onDraft,
  document,
}: {
  readonly draft: WorkflowDraft;
  readonly onDraft: (draft: WorkflowDraft) => void;
  readonly document: CompanyBundleDocument;
}): ReactElement {
  const keys = projectKeys(document);
  const held = new Set(draft.projects);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Runs on</CardTitle>
      </CardHeader>
      <CardBody className="flex flex-wrap gap-2">
        {keys.length === 0 ? (
          <p className="m-0 text-sm text-muted">This company declares no project yet.</p>
        ) : (
          keys.map((key) => (
            <label
              key={key}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-sm border px-3 py-2",
                held.has(key) ? "border-amber bg-amber/10" : "border-line hover:bg-raised"
              )}
            >
              <Checkbox
                checked={held.has(key)}
                label={`Run this workflow on ${key}`}
                onCheckedChange={(checked): void => {
                  const next = new Set(held);
                  if (checked) {
                    next.add(key);
                  } else {
                    next.delete(key);
                  }
                  onDraft({ ...draft, projects: [...next].sort() });
                }}
              />
              <span className="font-mono text-sm">{key}</span>
            </label>
          ))
        )}
      </CardBody>
    </Card>
  );
}

/** Every value the schema allows, plus whatever is held, so nothing is dropped. */
function offered(values: readonly string[], held: string): readonly string[] {
  return held === "" || values.includes(held) ? values : [held, ...values];
}

export function EditorFooter({
  edits,
  onCancel,
  onReview,
}: {
  readonly edits: number;
  readonly onCancel: () => void;
  readonly onReview: () => void;
}): ReactElement {
  return (
    <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
      <Button variant="quiet" onClick={onCancel}>
        Cancel
      </Button>
      <span className="flex-1" />
      {edits === 0 ? null : (
        <Button variant="primary" onClick={onReview}>
          Review changes ({edits}) →
        </Button>
      )}
    </footer>
  );
}
