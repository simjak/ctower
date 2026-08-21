import type { ReactElement } from "react";
import type { CompanyBundleValidationResult } from "@ctower/client";
import type { Answer } from "../../api/client";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono, PageHead } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import { shortDigest } from "../bundle";
import { Asking, Malformed, Refused, Unreachable } from "../states";
import { checkName } from "./checks";

/**
 * Step 2 — check the bundle.
 *
 * The registry runs its own checks and this step shows exactly what came back:
 * every check it ran, every warning it raised, and the digest the answer is
 * about. Nothing is summarised into a verdict the server did not give, and a
 * warning is never rounded down to a pass.
 */
export function CheckStep({
  answer,
}: {
  readonly answer: Answer<CompanyBundleValidationResult>;
}): ReactElement {
  switch (answer.kind) {
    case "asking":
      return (
        <>
          <PageHead title="Check the bundle" subtitle="Asking the registry" />
          <Asking what="Checking this company" />
        </>
      );
    case "refused":
      return (
        <>
          <PageHead title="Check the bundle" subtitle={<Chip tone="danger">refused</Chip>} />
          <Refused
            problem={answer.problem}
            action="Go back and change the company, then check again."
          />
        </>
      );
    case "unreachable":
      return (
        <>
          <PageHead title="Check the bundle" subtitle={<Chip tone="neutral">no answer</Chip>} />
          <Unreachable
            detail={answer.detail}
            action="Nothing was checked. Check again when ctower answers."
          />
        </>
      );
    case "malformed":
      return (
        <>
          <PageHead title="Check the bundle" subtitle={<Chip tone="amber">contract</Chip>} />
          <Malformed detail={answer.detail} />
        </>
      );
    case "answered":
      return <Result result={answer.value} />;
  }
}

function Result({ result }: { readonly result: CompanyBundleValidationResult }): ReactElement {
  const warned = result.checks.filter((check) => check.status === "warning").length;
  return (
    <>
      <PageHead
        title="Check the bundle"
        subtitle={
          <>
            {result.valid ? <Chip tone="ok">valid</Chip> : <Chip tone="danger">not valid</Chip>}
            <Mono className="text-muted" title={result.bundle_digest}>
              {shortDigest(result.bundle_digest)}
            </Mono>
          </>
        }
      />
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Checks</CardTitle>
            <span className="flex-1" />
            <Mono className="text-muted">
              {result.checks.length - warned} of {result.checks.length}
            </Mono>
          </CardHeader>
          <CardBody className="space-y-2">
            {result.checks.map((check) => (
              <div
                key={check.code}
                className="flex items-center gap-3 rounded-md border border-line px-4 py-2.5"
              >
                {check.status === "passed" ? <Mark name="done" /> : <Mark name="warn" />}
                <span className="min-w-0 flex-1 truncate text-sm text-fg">
                  {checkName(check.code)}
                </span>
                <Mono className="hidden text-muted sm:inline" title={check.code}>
                  {check.code}
                </Mono>
              </div>
            ))}
          </CardBody>
        </Card>

        {result.warnings.length === 0 ? null : (
          <Card>
            <CardHeader>
              <CardTitle>Warnings</CardTitle>
              <span className="flex-1" />
              <Chip tone="amber">{result.warnings.length}</Chip>
            </CardHeader>
            <CardBody className="space-y-1.5">
              {result.warnings.map((warning) => (
                <p key={warning} className="m-0 text-sm text-muted">
                  {warning}
                </p>
              ))}
            </CardBody>
          </Card>
        )}
      </div>
    </>
  );
}
