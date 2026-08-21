import { ChevronDown } from "lucide-react";
import type { ReactElement } from "react";
import type { BundleAction, CompanyBundlePlan } from "@ctower/client";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../../ui/primitives";
import { cn } from "../../ui/cn";
import { shortDigest } from "../bundle";
import { groupActions, kindLabel, movedCount } from "./actions";
import type { Group } from "./actions";

/**
 * The registry's plan, drawn the way a change is read: added, changed, removed,
 * unchanged, each row carrying the component it is about with the revision and
 * digest that pin it. The counts are the plan's own; nothing here decides what
 * moved.
 */
export function PlanDiff({ plan }: { readonly plan: CompanyBundlePlan }): ReactElement {
  const groups = groupActions(plan.actions);
  const moved = movedCount(plan.actions);

  return (
    <div className="space-y-4">
      {moved === 0 ? (
        <Card>
          <CardBody>
            <p className="m-0 text-sm text-muted">
              These edits change nothing the registry records. There is nothing to apply.
            </p>
          </CardBody>
        </Card>
      ) : null}

      {plan.warnings.length === 0 ? null : (
        <Card>
          <CardHeader>
            <CardTitle>Warnings</CardTitle>
            <span className="flex-1" />
            <Chip tone="amber">{plan.warnings.length}</Chip>
          </CardHeader>
          <CardBody className="space-y-1.5">
            {plan.warnings.map((warning) => (
              <p key={warning} className="m-0 text-sm text-muted">
                {warning}
              </p>
            ))}
          </CardBody>
        </Card>
      )}

      {groups.map((group) =>
        group.actions.length === 0 ? null : <GroupCard key={group.movement} group={group} />
      )}
    </div>
  );
}

const SIGN_INK: Readonly<Record<string, string>> = {
  "+": "text-ok",
  "~": "text-amber-strong",
  "-": "text-danger",
  "=": "text-muted",
};

/**
 * A group of the plan's actions. What moved is open; what did not is folded
 * away behind its own count, because forty-seven rows saying `unchanged` bury
 * the two that are the change. Nothing is hidden — the fold is one click and it
 * states how much is behind it.
 */
function GroupCard({ group }: { readonly group: Group }): ReactElement {
  const rows = (
    <CardBody className="space-y-1">
      {group.actions.map((action) => (
        <ActionRow
          key={`${action.kind}:${action.component.kind}:${action.component.key}`}
          action={action}
          sign={group.sign}
        />
      ))}
    </CardBody>
  );

  const head = (
    <>
      <Mono aria-hidden className={cn("text-md", SIGN_INK[group.sign])}>
        {group.sign}
      </Mono>
      <CardTitle>{group.label}</CardTitle>
      <span className="flex-1" />
      <Mono className="text-muted">{group.actions.length}</Mono>
    </>
  );

  if (group.movement !== "keeps") {
    return (
      <Card>
        <CardHeader>{head}</CardHeader>
        {rows}
      </Card>
    );
  }

  return (
    <Card>
      <details>
        <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-3.5 hover:bg-raised">
          {head}
          <ChevronDown className="size-4 shrink-0 text-muted" />
        </summary>
        <div className="border-t border-line">{rows}</div>
      </details>
    </Card>
  );
}

function ActionRow({
  action,
  sign,
}: {
  readonly action: BundleAction;
  readonly sign: string;
}): ReactElement {
  const component = action.component;
  return (
    <div className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-raised">
      <Mono aria-hidden className={cn("w-3 shrink-0", SIGN_INK[sign])}>
        {sign}
      </Mono>
      <span className="min-w-0 flex-1 truncate text-sm text-fg">{component.key}</span>
      <Mono className="hidden shrink-0 text-muted md:inline" title={component.content_digest}>
        {shortDigest(component.content_digest)}
      </Mono>
      <Mono className="shrink-0 text-muted">r{component.revision}</Mono>
      <Chip tone="neutral" title={component.kind}>
        {kindLabel(action.kind)}
      </Chip>
    </div>
  );
}
