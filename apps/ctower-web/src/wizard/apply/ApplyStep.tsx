import { ShieldAlert } from "lucide-react";
import type { ReactElement } from "react";
import type { CompanyBundleCommandResult, CompanyBundlePlan } from "@ctower/client";
import type { Answer } from "../../api/client";
import { Badge, Card, CardBody, CardHeader, CardTitle, Mono, PageHead } from "../../ui/primitives";
import { Checkbox } from "../../ui/form";
import { cn } from "../../ui/cn";
import { shortDigest } from "../bundle";
import { Asking, Malformed, Refused, Unreachable } from "../states";
import { movedCount } from "../review/actions";

/**
 * Step 4 — apply, and the gate in front of it.
 *
 * D30 puts this command on the operator's own authority. The gate is therefore
 * stated rather than implied: the screen says whose authority runs it, and the
 * control does not arm until the operator says so on this screen. There is no
 * path through this component that sends the command without that.
 */
export function ApplyStep({
  plan,
  answer,
  armed,
  onArm,
}: {
  readonly plan: CompanyBundlePlan;
  readonly answer: Answer<CompanyBundleCommandResult> | null;
  readonly armed: boolean;
  readonly onArm: (armed: boolean) => void;
}): ReactElement {
  if (answer !== null) {
    return <Outcome answer={answer} />;
  }

  const moved = movedCount(plan.actions);
  return (
    <>
      <PageHead
        title="Apply"
        subtitle={
          <>
            <Badge tone="accent">
              {moved} {moved === 1 ? "change" : "changes"}
            </Badge>
            <span>
              version <Mono>{plan.base_version}</Mono> → <Mono>{plan.base_version + 1}</Mono>
            </span>
          </>
        }
      />
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <ShieldAlert className="size-4 shrink-0 text-warn" />
            <CardTitle>Apply runs with operator authority</CardTitle>
          </CardHeader>
          <CardBody className="space-y-4">
            <p className="m-0 text-sm text-ink-2">
              This writes the company record. It is the operator&apos;s command, and ctower will
              refuse it from anyone else.
            </p>
            <label
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-md border px-4 py-3",
                "transition-colors duration-(--motion-duration-fast)",
                armed ? "border-warn bg-warn-bg" : "border-line-2 hover:bg-raised/50"
              )}
            >
              <Checkbox
                checked={armed}
                onCheckedChange={onArm}
                label="Confirm this runs with operator authority"
              />
              <span className="text-sm font-medium text-ink">
                I am applying this as the operator.
              </span>
            </label>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What is sent</CardTitle>
          </CardHeader>
          <CardBody className="space-y-1.5">
            <Line label="plan" value={plan.plan_digest} />
            <Line label="bundle" value={plan.proposed_bundle_digest} />
            <Line label="expects version" value={String(plan.base_version)} plain />
          </CardBody>
        </Card>
      </div>
    </>
  );
}

function Outcome({
  answer,
}: {
  readonly answer: Answer<CompanyBundleCommandResult>;
}): ReactElement {
  switch (answer.kind) {
    case "asking":
      return (
        <>
          <PageHead title="Apply" subtitle={<Badge tone="warn">sending</Badge>} />
          <Asking what="Applying, and waiting for ctower to accept it" />
        </>
      );
    case "refused":
      return (
        <>
          <PageHead title="Apply" subtitle={<Badge tone="refuse">refused</Badge>} />
          <Refused
            problem={answer.problem}
            action="Nothing was written. Go back, review the changes, and apply again."
          />
        </>
      );
    case "unreachable":
      return (
        <>
          <PageHead title="Apply" subtitle={<Badge tone="unknown">unknown</Badge>} />
          <Unreachable
            detail={answer.detail}
            action="Whether this was written is not known. Applying again reuses the same command, so it cannot write twice."
          />
        </>
      );
    case "malformed":
      return (
        <>
          <PageHead title="Apply" subtitle={<Badge tone="warn">contract</Badge>} />
          <Malformed detail={answer.detail} />
        </>
      );
    case "answered":
      return <Receipt receipt={answer.value} />;
  }
}

/**
 * The receipt, and the one thing it may not do: call a pending write done.
 * `durability_pending` is not acceptance, so it is not drawn as one.
 */
function Receipt({ receipt }: { readonly receipt: CompanyBundleCommandResult }): ReactElement {
  const accepted = receipt.durability_state === "accepted";
  return (
    <>
      <PageHead
        title="Apply"
        subtitle={
          accepted ? (
            <>
              <Badge tone="proven">applied</Badge>
              <span>
                now at version <Mono>{receipt.active_version}</Mono>
              </span>
            </>
          ) : (
            <Badge tone="warn">not yet durable</Badge>
          )
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>{accepted ? "Receipt" : "Sent, and not yet accepted"}</CardTitle>
          <span className="flex-1" />
          <Badge tone="neutral">
            {receipt.event_ids.length} {receipt.event_ids.length === 1 ? "event" : "events"}
          </Badge>
        </CardHeader>
        <CardBody className="space-y-1.5">
          {accepted ? null : (
            <p className="m-0 mb-2 text-sm text-ink-2">
              ctower took the command and has not confirmed it is durable. It is not applied until
              it says so.
            </p>
          )}
          <Line label="command" value={receipt.command_id} />
          <Line label="bundle" value={receipt.bundle_digest} />
          <Line label="plan" value={receipt.plan_digest} />
        </CardBody>
      </Card>
    </>
  );
}

function Line({
  label,
  value,
  plain,
}: {
  readonly label: string;
  readonly value: string;
  readonly plain?: boolean;
}): ReactElement {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-32 shrink-0 text-xs text-ink-3">{label}</span>
      <Mono className="min-w-0 truncate text-ink-2" title={value}>
        {plain === true ? value : shortDigest(value)}
      </Mono>
    </div>
  );
}
