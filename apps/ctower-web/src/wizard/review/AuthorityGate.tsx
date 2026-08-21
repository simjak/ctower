import type { ReactElement } from "react";
import type { CompanyBundlePlan } from "@ctower/client";
import { Card, CardBody, CardHeader, CardTitle, Mono } from "../../ui/primitives";
import { Checkbox } from "../../ui/form";
import { Mark } from "../../ui/marks";
import { cn } from "../../ui/cn";
import { shortDigest } from "../bundle";
import { movementOf } from "./actions";

/**
 * The gate in front of the command.
 *
 * D30 puts apply on the operator's own authority, so the screen says whose
 * authority runs it and the control does not arm until the operator says on
 * this screen that it is theirs. This is also where removing something is
 * finally spelled out: the rows said nothing about consequences, and this is
 * the moment one is being accepted.
 */
export function AuthorityGate({
  plan,
  armed,
  onArm,
}: {
  readonly plan: CompanyBundlePlan;
  readonly armed: boolean;
  readonly onArm: (armed: boolean) => void;
}): ReactElement {
  const retiring = plan.actions.filter((action) => movementOf(action.kind) === "removes").length;

  return (
    <Card>
      <CardHeader>
        <Mark name="warn" />
        <CardTitle>Apply runs with operator authority</CardTitle>
      </CardHeader>
      <CardBody>
        <p className="m-0 text-sm text-muted">
          This writes the company record. It is the operator&apos;s command, and ctower will refuse
          it from anyone else.
          {retiring === 0
            ? ""
            : ` ${String(retiring)} ${retiring === 1 ? "component retires" : "components retire"} on apply.`}
        </p>

        <dl className="m-0 mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
          <Term label="plan" value={shortDigest(plan.plan_digest)} title={plan.plan_digest} />
          <Term
            label="bundle"
            value={shortDigest(plan.proposed_bundle_digest)}
            title={plan.proposed_bundle_digest}
          />
          <Term label="expects version" value={String(plan.base_version)} />
        </dl>

        <label
          className={cn(
            "mt-4 flex cursor-pointer items-center gap-3 rounded-sm border px-4 py-3",
            armed ? "border-amber bg-amber/10" : "border-line hover:bg-raised"
          )}
        >
          <Checkbox
            checked={armed}
            onCheckedChange={onArm}
            label="Confirm this runs with operator authority"
          />
          <span className="text-sm font-medium text-fg">I am applying this as the operator.</span>
        </label>
      </CardBody>
    </Card>
  );
}

function Term({
  label,
  value,
  title,
}: {
  readonly label: string;
  readonly value: string;
  readonly title?: string;
}): ReactElement {
  return (
    <>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="m-0 min-w-0">
        <Mono className="truncate text-muted" title={title ?? value}>
          {value}
        </Mono>
      </dd>
    </>
  );
}
