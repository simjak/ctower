import type { ReactElement } from "react";
import type { ConsoleSessionAllowRequest } from "@ctower/client";
import { Field, Hint } from "../ui/form";
import { Button, Card, CardBody, CardHeader, CardTitle, Chip, Input } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { FACT_GROUPS, FIXED, requestFrom, withFact } from "./allowance";
import type { Draft, FactGroup } from "./allowance";

/**
 * The one thing this screen can do, and the whole truth about doing it.
 *
 * The consequence sits above the button rather than behind a confirmation.
 * `DESIGN.md` asks a destructive action to name what it does at the point of
 * action; here the consequence that matters is not the write but its
 * one-wayness — this console can hand out a terminal and cannot take one back —
 * so that is the sentence the operator reads with their hand on the control.
 */
const SOURCE =
  "Every fact here comes from the runner that started this terminal. The " +
  "allowance binds to all of them at once and stops meaning anything the " +
  "moment one of them moves on.";

export function AllowCard({
  draft,
  onDraft,
  onAllow,
  busy,
}: {
  readonly draft: Draft;
  readonly onDraft: (draft: Draft) => void;
  readonly onAllow: (body: ConsoleSessionAllowRequest) => void;
  readonly busy: boolean;
}): ReactElement {
  const body = requestFrom(draft);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Allow one terminal to be watched</CardTitle>
        <Hint text={SOURCE} />
        <span className="ml-auto flex items-center gap-1.5">
          <span className="text-2xs text-muted">fixed</span>
          {FIXED.map((value) => (
            <Chip key={value}>{value}</Chip>
          ))}
        </span>
      </CardHeader>
      <CardBody className="space-y-6">
        {FACT_GROUPS.map((group) => (
          <Group key={group.title} group={group} draft={draft} onDraft={onDraft} />
        ))}
        <div className="flex flex-wrap items-center justify-end gap-x-6 gap-y-2 border-t border-line pt-4">
          <p className="m-0 mr-auto flex items-start gap-2 text-xs text-muted">
            <Mark name="warn" className="mt-px" />
            Allows watching until this terminal ends. Taking it back is not reachable from here.
          </p>
          <Button
            variant="primary"
            disabled={body === null || busy}
            onClick={(): void => {
              if (body !== null) {
                onAllow(body);
              }
            }}
          >
            Allow watching
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function Group({
  group,
  draft,
  onDraft,
}: {
  readonly group: FactGroup;
  readonly draft: Draft;
  readonly onDraft: (draft: Draft) => void;
}): ReactElement {
  // `mx-0` and not `m-0`: the user agent's inline margin is the only one that
  // needs clearing, and zeroing the block margins too silently beats the card's
  // own vertical rhythm — which is exactly how the groups first shipped packed.
  return (
    <fieldset className="mx-0 min-w-0 border-0 p-0">
      {/* The rail's own group grammar, one level down: a group heading is a
          different kind of thing from a field label, so it is told apart by
          case and tracking rather than by being a slightly smaller grey. */}
      <legend className="mb-2.5 p-0 text-[10.5px] tracking-[0.1em] text-muted uppercase">
        {group.title}
      </legend>
      <div className="grid gap-3 md:grid-cols-3">
        {group.facts.map((fact) => (
          <Field key={fact.key} label={fact.label}>
            <Input
              // `Field` draws its label as text beside the control rather than
              // binding one to it, so on a screen with no placeholders every
              // box would reach a keyboard with no name at all. Named here
              // rather than in the shared primitive: changing `Field` would
              // reach four other screens this ticket does not own.
              aria-label={fact.label}
              className="mono"
              inputMode={fact.kind === "count" ? "numeric" : "text"}
              value={draft[fact.key]}
              onChange={(event): void => {
                onDraft(withFact(draft, fact.key, event.target.value));
              }}
            />
          </Field>
        ))}
      </div>
    </fieldset>
  );
}
