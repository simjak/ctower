import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Card, CardBody, CardHeader, CardTitle, Input, Select } from "../ui/primitives";
import { ACTIVITY_CLASSES } from "./draft";
import type { RouteDraft, StageDraft, TransitionDraft, WorkflowDraft } from "./draft";

/**
 * The three lists a workflow is made of: its stages, the moves between them,
 * and where a failure sends the work instead.
 *
 * They are edited as lists and not as a canvas. A stage key, the class of work
 * it is, and the exact predicate a move is allowed under are all typed values
 * the registry will check; a drag-and-drop graph would make the same document
 * with more ways to be wrong about it. Order is the operator's, because the
 * order stages are written in is the order they are recorded in.
 */
export function StageRows({
  draft,
  onDraft,
}: {
  readonly draft: WorkflowDraft;
  readonly onDraft: (draft: WorkflowDraft) => void;
}): ReactElement {
  const stages = draft.stages;
  const replace = (next: readonly StageDraft[]): void => {
    onDraft({ ...draft, stages: next });
  };

  return (
    <Section
      title="Stages"
      count={stages.length}
      addLabel="Add a stage"
      onAdd={(): void => {
        replace([...stages, { key: "", activityClass: "work" }]);
      }}
      empty="No stage yet. A workflow needs at least one."
    >
      {stages.map((stage, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            aria-label={`Stage ${String(index + 1)} key`}
            className="max-w-sm font-mono"
            placeholder="review"
            spellCheck={false}
            value={stage.key}
            onChange={(event): void => {
              replace(swap(stages, index, { ...stage, key: event.target.value }));
            }}
          />
          <Select
            aria-label={`Stage ${String(index + 1)} class`}
            className="w-40"
            value={stage.activityClass}
            onChange={(event): void => {
              const chosen = ACTIVITY_CLASSES.find((value) => value === event.target.value);
              replace(swap(stages, index, { ...stage, activityClass: chosen ?? "work" }));
            }}
          >
            {ACTIVITY_CLASSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </Select>
          <Move
            index={index}
            length={stages.length}
            onMove={(to): void => {
              replace(moved(stages, index, to));
            }}
          />
          <Remove
            label={`Remove stage ${String(index + 1)}`}
            onRemove={(): void => {
              replace(stages.filter((_, at) => at !== index));
            }}
          />
        </div>
      ))}
    </Section>
  );
}

/** Where work goes next, and the exact predicate the record allows it under. */
export function TransitionRows({
  draft,
  onDraft,
}: {
  readonly draft: WorkflowDraft;
  readonly onDraft: (draft: WorkflowDraft) => void;
}): ReactElement {
  const rows = draft.transitions;
  const replace = (next: readonly TransitionDraft[]): void => {
    onDraft({ ...draft, transitions: next });
  };

  return (
    <Section
      title="Moves"
      count={rows.length}
      addLabel="Add a move"
      onAdd={(): void => {
        replace([...rows, { from: "", to: "", predicate: "" }]);
      }}
      empty="No move yet. Without one, work cannot leave the entry stage."
    >
      {rows.map((row, index) => (
        <div key={index} className="flex items-center gap-2">
          <StagePick
            label={`Move ${String(index + 1)} from`}
            stages={draft.stages}
            value={row.from}
            onPick={(value): void => {
              replace(swap(rows, index, { ...row, from: value }));
            }}
          />
          <span aria-hidden className="text-muted">
            →
          </span>
          <StagePick
            label={`Move ${String(index + 1)} to`}
            stages={draft.stages}
            value={row.to}
            onPick={(value): void => {
              replace(swap(rows, index, { ...row, to: value }));
            }}
          />
          <Input
            aria-label={`Move ${String(index + 1)} predicate`}
            className="font-mono"
            placeholder="entry.ready@1"
            spellCheck={false}
            value={row.predicate}
            onChange={(event): void => {
              replace(swap(rows, index, { ...row, predicate: event.target.value }));
            }}
          />
          <Remove
            label={`Remove move ${String(index + 1)}`}
            onRemove={(): void => {
              replace(rows.filter((_, at) => at !== index));
            }}
          />
        </div>
      ))}
    </Section>
  );
}

/** Where a named failure sends the work instead of forward. */
export function RouteRows({
  draft,
  onDraft,
}: {
  readonly draft: WorkflowDraft;
  readonly onDraft: (draft: WorkflowDraft) => void;
}): ReactElement {
  const rows = draft.routes;
  const replace = (next: readonly RouteDraft[]): void => {
    onDraft({ ...draft, routes: next });
  };

  return (
    <Section
      title="Failure routes"
      count={rows.length}
      addLabel="Add a route"
      onAdd={(): void => {
        replace([...rows, { from: "", failureClass: "", to: "" }]);
      }}
      empty="None. A failure with no route declared does not move the work."
    >
      {rows.map((row, index) => (
        <div key={index} className="flex items-center gap-2">
          <StagePick
            label={`Route ${String(index + 1)} from`}
            stages={draft.stages}
            value={row.from}
            onPick={(value): void => {
              replace(swap(rows, index, { ...row, from: value }));
            }}
          />
          <Input
            aria-label={`Route ${String(index + 1)} reason`}
            className="font-mono"
            placeholder="review.rejected@1"
            spellCheck={false}
            value={row.failureClass}
            onChange={(event): void => {
              replace(swap(rows, index, { ...row, failureClass: event.target.value }));
            }}
          />
          <span aria-hidden className="text-muted">
            →
          </span>
          <StagePick
            label={`Route ${String(index + 1)} to`}
            stages={draft.stages}
            value={row.to}
            onPick={(value): void => {
              replace(swap(rows, index, { ...row, to: value }));
            }}
          />
          <Remove
            label={`Remove route ${String(index + 1)}`}
            onRemove={(): void => {
              replace(rows.filter((_, at) => at !== index));
            }}
          />
        </div>
      ))}
    </Section>
  );
}

function Section({
  title,
  count,
  addLabel,
  onAdd,
  empty,
  children,
}: {
  readonly title: string;
  readonly count: number;
  readonly addLabel: string;
  readonly onAdd: () => void;
  readonly empty: string;
  readonly children: ReactElement[];
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <span className="flex-1" />
        <Button size="sm" variant="ghost" onClick={onAdd}>
          <Plus /> {addLabel}
        </Button>
      </CardHeader>
      <CardBody className="space-y-2">
        {count === 0 ? <p className="m-0 text-sm text-muted">{empty}</p> : children}
      </CardBody>
    </Card>
  );
}

/**
 * A stage this workflow declares. A row may still name one it does not — a key
 * typed before the stage was added, or a stage taken out from under it — so the
 * held value is always offered and the row never silently repoints itself.
 */
function StagePick({
  label,
  stages,
  value,
  onPick,
}: {
  readonly label: string;
  readonly stages: readonly StageDraft[];
  readonly value: string;
  readonly onPick: (value: string) => void;
}): ReactElement {
  const declared = stages.map((stage) => stage.key).filter((key) => key.length > 0);
  const offered = declared.includes(value) || value === "" ? declared : [value, ...declared];
  return (
    <Select
      aria-label={label}
      className="font-mono"
      value={value}
      onChange={(event): void => {
        onPick(event.target.value);
      }}
    >
      <option value="">—</option>
      {offered.map((key) => (
        <option key={key} value={key}>
          {key}
        </option>
      ))}
    </Select>
  );
}

function Move({
  index,
  length,
  onMove,
}: {
  readonly index: number;
  readonly length: number;
  readonly onMove: (to: number) => void;
}): ReactElement {
  return (
    <span className="flex shrink-0">
      <Button
        size="sm"
        variant="quiet"
        className="px-1.5"
        aria-label={`Move stage ${String(index + 1)} earlier`}
        disabled={index === 0}
        onClick={(): void => {
          onMove(index - 1);
        }}
      >
        <ArrowUp />
      </Button>
      <Button
        size="sm"
        variant="quiet"
        className="px-1.5"
        aria-label={`Move stage ${String(index + 1)} later`}
        disabled={index === length - 1}
        onClick={(): void => {
          onMove(index + 1);
        }}
      >
        <ArrowDown />
      </Button>
    </span>
  );
}

function Remove({
  label,
  onRemove,
}: {
  readonly label: string;
  readonly onRemove: () => void;
}): ReactElement {
  return (
    <Button
      size="sm"
      variant="quiet"
      className="shrink-0 px-1.5"
      aria-label={label}
      onClick={onRemove}
    >
      <X />
    </Button>
  );
}

function swap<T>(rows: readonly T[], index: number, row: T): readonly T[] {
  return rows.map((held, at) => (at === index ? row : held));
}

function moved<T>(rows: readonly T[], from: number, to: number): readonly T[] {
  const next = [...rows];
  const held = next[from];
  if (held === undefined || to < 0 || to >= next.length) {
    return rows;
  }
  next.splice(from, 1);
  next.splice(to, 0, held);
  return next;
}
