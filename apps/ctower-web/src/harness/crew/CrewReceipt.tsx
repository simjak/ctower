import type { ReactElement, ReactNode } from "react";
import type { CompanyBundleCommandResult, SeatCredentialReceipt } from "@ctower/client";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import type { MarkName } from "../../ui/marks";
import { Malformed, Refused, Unreachable } from "../../wizard/states";
import type { Answer } from "../../api/client";
import { AddressLine } from "./Address";

/**
 * What happened, in the order it happened, and no further.
 *
 * Two commands ran, or one did and the other never left. That is the fact an
 * operator needs when something goes wrong here — an address that was never sent
 * is a different situation from one that was refused — so each half carries its
 * own outcome and neither borrows the other's.
 *
 * A step nothing has been reported about draws no mark. `durability_pending` is
 * not acceptance and is never drawn as one.
 */
export function CrewReceipt({
  subject,
  moving,
  bound,
  address,
}: {
  readonly subject: string;
  /** Whether the profile half had anything to write at all. */
  readonly moving: boolean;
  readonly bound: Answer<CompanyBundleCommandResult> | null;
  readonly address: Answer<SeatCredentialReceipt> | null;
}): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Defining {subject}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <Step
          title="The crew"
          mark={bindingMark(moving, bound)}
          summary={<Binding bound={bound} />}
        >
          <Detail answer={bound} nothing="Nothing was written to the company record." />
        </Step>
        <Step
          title="The address"
          mark={addressMark(address)}
          summary={<Address address={address} />}
        >
          <Detail answer={address} nothing="No address was minted." />
        </Step>
      </CardBody>
    </Card>
  );
}

function Step({
  title,
  mark,
  summary,
  children,
}: {
  readonly title: string;
  readonly mark: MarkName | null;
  readonly summary: ReactNode;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {mark === null ? <span className="inline-block w-[1.4em]" /> : <Mark name={mark} />}
        <span className="text-sm font-medium text-fg">{title}</span>
        {summary}
      </div>
      <div className="mt-2 ml-[1.4em]">{children}</div>
    </div>
  );
}

function Binding({
  bound,
}: {
  readonly bound: Answer<CompanyBundleCommandResult> | null;
}): ReactElement {
  if (bound === null) {
    return <Chip>already bound</Chip>;
  }
  switch (bound.kind) {
    case "asking":
      return <Chip tone="amber">writing</Chip>;
    case "refused":
      return <Chip tone="danger">{bound.problem.code}</Chip>;
    case "unreachable":
      return <Chip>unknown</Chip>;
    case "malformed":
      return <Chip tone="amber">contract</Chip>;
    case "answered":
      return bound.value.durability_state === "accepted" ? (
        <>
          <Chip tone="ok">bound</Chip>
          <span className="text-sm text-muted">
            now at version <Mono>{bound.value.active_version}</Mono>
          </span>
        </>
      ) : (
        <Chip tone="amber">not yet durable</Chip>
      );
  }
}

function Address({
  address,
}: {
  readonly address: Answer<SeatCredentialReceipt> | null;
}): ReactElement {
  if (address === null) {
    return <Chip>not sent</Chip>;
  }
  switch (address.kind) {
    case "asking":
      return <Chip tone="amber">minting</Chip>;
    case "refused":
      return <Chip tone="danger">{address.problem.code}</Chip>;
    case "unreachable":
      return <Chip>unknown</Chip>;
    case "malformed":
      return <Chip tone="amber">contract</Chip>;
    case "answered":
      return <AddressLine receipt={address.value} mark={false} />;
  }
}

/** The full state under a step, and only when there is one worth reading. */
function Detail({
  answer,
  nothing,
}: {
  readonly answer: Answer<unknown> | null;
  readonly nothing: string;
}): ReactElement | null {
  if (answer === null || answer.kind === "asking" || answer.kind === "answered") {
    return null;
  }
  switch (answer.kind) {
    case "refused":
      return <Refused problem={answer.problem} action={nothing} />;
    case "unreachable":
      return (
        <Unreachable
          detail={answer.detail}
          action="Whether this was recorded is not known. Sending again reuses the same command."
        />
      );
    case "malformed":
      return <Malformed detail={answer.detail} />;
  }
}

function bindingMark(
  moving: boolean,
  bound: Answer<CompanyBundleCommandResult> | null
): MarkName | null {
  if (bound === null) {
    return moving ? "idle" : "done";
  }
  switch (bound.kind) {
    case "asking":
      return "working";
    case "refused":
      return "dead";
    case "unreachable":
    case "malformed":
      return null;
    case "answered":
      return bound.value.durability_state === "accepted" ? "done" : "warn";
  }
}

function addressMark(address: Answer<SeatCredentialReceipt> | null): MarkName | null {
  if (address === null) {
    return "idle";
  }
  switch (address.kind) {
    case "asking":
      return "working";
    case "refused":
      return "dead";
    case "unreachable":
    case "malformed":
      return null;
    case "answered": {
      if (address.value.durability_state !== "accepted") {
        return "working";
      }
      return address.value.state === "active" ? "done" : "dead";
    }
  }
}
