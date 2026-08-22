import type { ReactElement } from "react";
import type { SeatCredentialIssueRequest } from "@ctower/client";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../../ui/primitives";
import { Checkbox } from "../../ui/form";
import { Mark } from "../../ui/marks";
import { cn } from "../../ui/cn";
import { shortDigest } from "../../wizard/bundle";
import { PlanDiff } from "../../wizard/review/PlanDiff";
import { movedCount } from "../../wizard/review/actions";
import { Asking, Malformed, Refused, Unreachable } from "../../wizard/states";
import type { Proposal } from "./useCrewAct";
import type { Answer } from "../../api/client";

/**
 * What defining this crew would do, both halves, before anything is written.
 *
 * The registry's plan covers the first half and nothing covers the second —
 * `issueSeatCredential` has no dry run — so the address is shown as the exact
 * request that will be sent. That difference is real and the screen does not
 * paper over it: one half has been checked by ctower, the other has been read by
 * the operator.
 */
export function CrewReview({
  subject,
  binding,
  body,
  armed,
  onArm,
}: {
  readonly subject: string;
  readonly binding: Answer<Proposal> | null;
  readonly body: SeatCredentialIssueRequest;
  readonly armed: boolean;
  readonly onArm: (armed: boolean) => void;
}): ReactElement {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>The crew</CardTitle>
          <span className="flex-1" />
          <Mono className="text-muted">{subject}</Mono>
        </CardHeader>
        <CardBody>
          <Binding binding={binding} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>The address</CardTitle>
          <span className="flex-1" />
          <Chip tone="amber">not yet minted</Chip>
        </CardHeader>
        <CardBody>
          <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1">
            <Term label="project" value={body.project_key} />
            <Term label="seat" value={body.seat_key} />
            <Term label="can do" value={body.scopes.join(" · ")} />
            <Term label="lives at" value={body.credential_ref} />
            <Term
              label="fingerprint"
              value={shortDigest(body.credential_digest)}
              title={body.credential_digest}
            />
          </dl>
          <p className="mt-3 mb-0 text-xs text-muted">
            ctower records the reference and the fingerprint. The credential itself is not sent.
          </p>
        </CardBody>
      </Card>

      {ready(binding) ? <Gate armed={armed} onArm={onArm} moving={binding !== null} /> : null}
    </div>
  );
}

/** Whether both halves can be sent: the binding is settled and nothing refused it. */
export function ready(binding: Answer<Proposal> | null): boolean {
  return binding === null || (binding.kind === "answered" && binding.value.valid);
}

function Binding({ binding }: { readonly binding: Answer<Proposal> | null }): ReactElement {
  if (binding === null) {
    return (
      <p className="m-0 flex items-center gap-2 text-sm text-muted">
        <Mark name="done" />
        The company already binds this profile to this crew. Nothing is written.
      </p>
    );
  }
  switch (binding.kind) {
    case "asking":
      return <Asking what="Working out what would change" />;
    case "refused":
      return (
        <Refused problem={binding.problem} action="Nothing was planned. Go back and change it." />
      );
    case "unreachable":
      return (
        <Unreachable detail={binding.detail} action="No plan was made. Nothing has been written." />
      );
    case "malformed":
      return <Malformed detail={binding.detail} />;
    case "answered":
      return <Planned proposal={binding.value} />;
  }
}

function Planned({ proposal }: { readonly proposal: Proposal }): ReactElement {
  const moved = movedCount(proposal.plan.actions);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {proposal.valid ? <Chip tone="ok">valid</Chip> : <Chip tone="danger">not valid</Chip>}
        <Chip tone="amber">{moved} would move</Chip>
        <span className="text-sm text-muted">
          version <Mono>{proposal.plan.base_version}</Mono> →{" "}
          <Mono>{proposal.plan.base_version + 1}</Mono>
        </span>
      </div>
      <PlanDiff plan={proposal.plan} />
    </div>
  );
}

/**
 * The one confirmation, covering both commands.
 *
 * D30 puts these on the operator's own authority and ctower refuses them from
 * anyone else, so the screen says whose authority runs them and the control does
 * not arm until the operator says on this screen that it is theirs.
 */
function Gate({
  armed,
  onArm,
  moving,
}: {
  readonly armed: boolean;
  readonly onArm: (armed: boolean) => void;
  readonly moving: boolean;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <Mark name="warn" />
        <CardTitle>This runs with operator authority</CardTitle>
      </CardHeader>
      <CardBody>
        <p className="m-0 text-sm text-muted">
          {moving
            ? "This writes the company record, then mints the address. If the record refuses, no address is minted."
            : "This mints a live address. It answers until it is revoked."}
        </p>
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
          <span className="text-sm font-medium text-fg">
            I am defining this crew as the operator.
          </span>
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
        <Mono className="block truncate text-muted" title={title ?? value}>
          {value}
        </Mono>
      </dd>
    </>
  );
}
