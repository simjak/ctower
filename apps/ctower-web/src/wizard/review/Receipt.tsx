import { ArrowLeft, RotateCw } from "lucide-react";
import type { ReactElement } from "react";
import type { CompanyBundleCommandResult } from "@ctower/client";
import type { Answer } from "../../api/client";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Chip,
  Mono,
  PageHead,
} from "../../ui/primitives";
import { Asking, Malformed, Refused, Unreachable } from "../states";
import { shortDigest } from "../bundle";

/**
 * What came back, and the one thing it may not do: call a pending write done.
 * `durability_pending` is not acceptance, so it is not drawn as one and the
 * version does not move.
 *
 * Three of these outcomes tell the operator that sending again is safe, so
 * sending again is a control here and not an instruction to reload the page.
 * It is the same command under the same idempotency key — that is the whole
 * reason the promise can be made.
 */
export function Receipt({
  applied,
  onRetry,
  onBack,
}: {
  readonly applied: Answer<CompanyBundleCommandResult>;
  readonly onRetry: (() => void) | null;
  readonly onBack: () => void;
}): ReactElement {
  return (
    <>
      <Outcome applied={applied} />
      <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
        <Button variant="quiet" disabled={applied.kind === "asking"} onClick={onBack}>
          <ArrowLeft /> Back to the definition
        </Button>
        <span className="flex-1" />
        {onRetry === null ? null : (
          <Button variant="primary" onClick={onRetry}>
            <RotateCw /> Send the same command again
          </Button>
        )}
      </footer>
    </>
  );
}

function Outcome({
  applied,
}: {
  readonly applied: Answer<CompanyBundleCommandResult>;
}): ReactElement {
  switch (applied.kind) {
    case "asking":
      return (
        <>
          <PageHead title="Apply" subtitle={<Chip tone="amber">sending</Chip>} />
          <Asking what="Applying, and waiting for ctower to accept it" />
        </>
      );
    case "refused":
      return (
        <>
          <PageHead title="Apply" subtitle={<Chip tone="danger">refused</Chip>} />
          <Refused
            problem={applied.problem}
            action="Nothing was written. Go back and review the changes again."
          />
        </>
      );
    case "unreachable":
      return (
        <>
          <PageHead title="Apply" subtitle={<Chip>unknown</Chip>} />
          <Unreachable
            detail={applied.detail}
            action="Whether this was written is not known. Applying again reuses the same command, so it cannot write twice."
          />
        </>
      );
    case "malformed":
      return (
        <>
          <PageHead title="Apply" subtitle={<Chip tone="amber">contract</Chip>} />
          <Malformed detail={applied.detail} />
        </>
      );
    case "answered":
      return <Written receipt={applied.value} />;
  }
}

function Written({ receipt }: { readonly receipt: CompanyBundleCommandResult }): ReactElement {
  const accepted = receipt.durability_state === "accepted";
  return (
    <>
      <PageHead
        title="Apply"
        subtitle={
          accepted ? (
            <>
              <Chip tone="ok">applied</Chip>
              <span>
                now at version <Mono>{receipt.active_version}</Mono>
              </span>
            </>
          ) : (
            <Chip tone="amber">not yet durable</Chip>
          )
        }
      />
      <Card>
        <CardHeader>
          <CardTitle>{accepted ? "Receipt" : "Sent, and not yet accepted"}</CardTitle>
          <span className="flex-1" />
          <Chip>
            {receipt.event_ids.length} {receipt.event_ids.length === 1 ? "event" : "events"}
          </Chip>
        </CardHeader>
        <CardBody className="space-y-1.5">
          {accepted ? null : (
            <p className="m-0 mb-2 text-sm text-muted">
              ctower took the command and has not confirmed it is durable. It is not applied until
              it says so.
            </p>
          )}
          <Line label="command" value={receipt.command_id} />
          <Line
            label="bundle"
            value={shortDigest(receipt.bundle_digest)}
            title={receipt.bundle_digest}
          />
          <Line label="plan" value={shortDigest(receipt.plan_digest)} title={receipt.plan_digest} />
        </CardBody>
      </Card>
    </>
  );
}

function Line({
  label,
  value,
  title,
}: {
  readonly label: string;
  readonly value: string;
  readonly title?: string;
}): ReactElement {
  return (
    <div className="flex items-baseline gap-4">
      <span className="w-32 shrink-0 text-xs text-muted">{label}</span>
      <Mono className="min-w-0 truncate text-muted" title={title ?? value}>
        {value}
      </Mono>
    </div>
  );
}
