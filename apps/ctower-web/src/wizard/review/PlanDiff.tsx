import { ChevronDown } from "lucide-react";
import type { ReactElement } from "react";
import type { BundleAction, CompanyBundleDocument, CompanyBundlePlan } from "@ctower/client";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../../ui/primitives";
import { cn } from "../../ui/cn";
import { groupActions, kindLabel, movedCount } from "./actions";
import type { Group } from "./actions";

/**
 * The registry's plan, drawn the way a change is read: added, changed, removed,
 * unchanged, each row naming the thing it is about. The counts are the plan's
 * own; nothing here decides what moved.
 *
 * A row says what a person would say out loud — the name the payload gave the
 * thing, and what kind of thing it is. The key that pins it, the digest that
 * proves it and the revision it sits at are all machine text: they are what the
 * apply sends and what the receipt is checked against, and they say nothing to
 * the operator reading a diff.
 */
export function PlanDiff({
  plan,
  document,
}: {
  readonly plan: CompanyBundlePlan;
  /** The proposed bundle, which is where a component's own name lives. */
  readonly document: CompanyBundleDocument;
}): ReactElement {
  const groups = groupActions(plan.actions);
  const moved = movedCount(plan.actions);
  const names = namesIn(document);

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
        group.actions.length === 0 ? null : (
          <GroupCard key={group.movement} group={group} names={names} />
        )
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
function GroupCard({
  group,
  names,
}: {
  readonly group: Group;
  readonly names: ReadonlyMap<string, string>;
}): ReactElement {
  const rows = (
    <CardBody className="space-y-1">
      {group.actions.map((action) => (
        <ActionRow
          key={`${action.kind}:${action.component.kind}:${action.component.key}`}
          action={action}
          sign={group.sign}
          names={names}
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
  names,
}: {
  readonly action: BundleAction;
  readonly sign: string;
  readonly names: ReadonlyMap<string, string>;
}): ReactElement {
  const component = action.component;
  const reference = `${component.kind}:${component.key}`;
  return (
    <div className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-raised">
      <Mono aria-hidden className={cn("w-3 shrink-0", SIGN_INK[sign])}>
        {sign}
      </Mono>
      {/* A component the proposed bundle does not name is still a real row.
          It says what kind of thing it is, which is the one true thing left to
          say about it — its key would say nothing to anyone. */}
      <span className="min-w-0 flex-1 truncate text-sm text-fg">
        {names.get(reference) ?? <span className="text-muted">Unnamed</span>}
      </span>
      <span className="shrink-0 text-xs text-muted">{word(component.kind)}</span>
      <Chip tone="neutral">{kindLabel(action.kind)}</Chip>
    </div>
  );
}

/** The kind, as a person reads it: the record's own word, unpunctuated. */
function word(kind: string): string {
  return kind.replace(/_/g, " ");
}

/**
 * What each component in the proposed bundle is called, under the kind and key
 * that identify it. A plan action carries a reference and no payload, so the
 * name has to come from the document the plan was computed over — which is the
 * same document the apply sends, so the two can never be about different bytes.
 */
function namesIn(document: CompanyBundleDocument): ReadonlyMap<string, string> {
  const names = new Map<string, string>();
  for (const resource of document.resources) {
    const name = resource.payload.display_name;
    if (typeof name === "string" && name.length > 0) {
      names.set(`${resource.component.kind}:${resource.component.key}`, name);
    }
  }
  return names;
}
