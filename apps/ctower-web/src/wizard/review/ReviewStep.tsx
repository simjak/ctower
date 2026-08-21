import { ChevronDown } from "lucide-react";
import type { ReactElement } from "react";
import type { BundleAction, CompanyBundlePlan } from "@ctower/client";
import type { Answer } from "../../api/client";
import { Badge, Card, CardBody, CardHeader, CardTitle, Mono, PageHead } from "../../ui/primitives";
import { cn } from "../../ui/cn";
import { shortDigest } from "../bundle";
import { Asking, Malformed, Refused, Unreachable } from "../states";
import { groupActions, kindLabel, movedCount } from "./actions";
import type { Group } from "./actions";

/**
 * Step 3 — review changes.
 *
 * The registry's plan, drawn the way a change is read: added, changed, removed,
 * unchanged, each row carrying the component it is about and the revision and
 * digest that pin it. The counts are the plan's own; nothing here decides what
 * moved.
 */
export function ReviewStep({
  answer,
}: {
  readonly answer: Answer<CompanyBundlePlan>;
}): ReactElement {
  switch (answer.kind) {
    case "asking":
      return (
        <>
          <PageHead title="Review changes" subtitle="Asking the registry" />
          <Asking what="Working out what would change" />
        </>
      );
    case "refused":
      return (
        <>
          <PageHead title="Review changes" subtitle={<Badge tone="refuse">refused</Badge>} />
          <Refused
            problem={answer.problem}
            action="Go back and change the company, then review again."
          />
        </>
      );
    case "unreachable":
      return (
        <>
          <PageHead title="Review changes" subtitle={<Badge tone="unknown">no answer</Badge>} />
          <Unreachable
            detail={answer.detail}
            action="No plan was made. This is not an empty change set."
          />
        </>
      );
    case "malformed":
      return (
        <>
          <PageHead title="Review changes" subtitle={<Badge tone="warn">contract</Badge>} />
          <Malformed detail={answer.detail} />
        </>
      );
    case "answered":
      return <Plan plan={answer.value} />;
  }
}

function Plan({ plan }: { readonly plan: CompanyBundlePlan }): ReactElement {
  const groups = groupActions(plan.actions);
  const moved = movedCount(plan.actions);

  return (
    <>
      <PageHead
        title="Review changes"
        subtitle={
          <>
            {moved === 0 ? (
              <Badge tone="neutral">no change</Badge>
            ) : (
              <Badge tone="info">
                {moved} of {plan.actions.length} move
              </Badge>
            )}
            <span>
              from version <Mono>{plan.base_version}</Mono>
            </span>
            <Mono className="text-ink-4" title={plan.plan_digest}>
              {shortDigest(plan.plan_digest)}
            </Mono>
          </>
        }
      />
      <div className="space-y-4">
        {moved === 0 ? (
          <Card>
            <CardBody>
              <p className="m-0 text-sm text-ink-2">
                This company already looks exactly like this. Applying it would change nothing.
              </p>
            </CardBody>
          </Card>
        ) : null}

        {plan.warnings.length === 0 ? null : (
          <Card>
            <CardHeader>
              <CardTitle>Warnings</CardTitle>
              <span className="flex-1" />
              <Badge tone="warn">{plan.warnings.length}</Badge>
            </CardHeader>
            <CardBody className="space-y-1.5">
              {plan.warnings.map((warning) => (
                <p key={warning} className="m-0 text-sm text-ink-2">
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
    </>
  );
}

const SIGN_INK: Readonly<Record<string, string>> = {
  "+": "text-proven",
  "~": "text-warn",
  "-": "text-refuse",
  "=": "text-ink-4",
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
      <Mono aria-hidden className={cn("text-base", SIGN_INK[group.sign])}>
        {group.sign}
      </Mono>
      <CardTitle>{group.label}</CardTitle>
      <span className="flex-1" />
      <Mono className="text-ink-3">{group.actions.length}</Mono>
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
        <summary className="flex cursor-pointer list-none items-center gap-3 px-5 py-3.5 hover:bg-raised/50">
          {head}
          <ChevronDown className="size-4 shrink-0 text-ink-4" />
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
    <div className="flex items-center gap-3 rounded-md px-2 py-1.5 hover:bg-raised/60">
      <Mono aria-hidden className={cn("w-3 shrink-0", SIGN_INK[sign])}>
        {sign}
      </Mono>
      <span className="min-w-0 flex-1 truncate text-sm text-ink">{component.key}</span>
      <Mono className="hidden shrink-0 text-ink-4 md:inline" title={component.content_digest}>
        {shortDigest(component.content_digest)}
      </Mono>
      <Mono className="shrink-0 text-ink-3">r{component.revision}</Mono>
      <Badge tone="neutral" title={component.kind}>
        {kindLabel(action.kind)}
      </Badge>
    </div>
  );
}
