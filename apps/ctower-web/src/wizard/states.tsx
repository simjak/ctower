import { Loader, TriangleAlert, WifiOff } from "lucide-react";
import type { ReactElement } from "react";
import type { Problem } from "@ctower/client";
import { Badge, Mono } from "../ui/primitives";

/** A call is out. */
export function Asking({ what }: { readonly what: string }): ReactElement {
  return (
    <p className="m-0 flex items-center gap-2 py-6 text-[13px] text-ink-3">
      <Loader className="size-3.5 animate-spin text-accent" />
      {what}
    </p>
  );
}

/**
 * The API answered, and the answer was no.
 *
 * Fact, then next action, and nothing else: the code the server used, the
 * detail it wrote, and any unmet facts it listed. The wizard never restates a
 * refusal in its own words, because the registry's words are the ones the
 * operator will meet again in the log and in the CLI.
 */
export function Refused({
  problem,
  action,
}: {
  readonly problem: Problem;
  readonly action: string;
}): ReactElement {
  return (
    <div className="rounded-lg border border-refuse-line bg-refuse-bg p-4">
      <div className="flex items-start gap-2.5">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-refuse" />
        <div className="min-w-0 flex-1">
          <p className="m-0 text-[13px] font-medium text-ink">{problem.detail}</p>
          {problem.unmet_facts !== undefined && problem.unmet_facts.length > 0 ? (
            <ul className="mt-2 mb-0 list-none space-y-0.5 p-0">
              {problem.unmet_facts.map((fact) => (
                <li key={fact}>
                  <Mono className="text-ink-2">{fact}</Mono>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="mt-1.5 mb-0 text-[12px] text-ink-2">{action}</p>
        </div>
        <Badge tone="refuse" title={`${problem.title} · ${String(problem.status)}`}>
          <Mono>{problem.code}</Mono>
        </Badge>
      </div>
    </div>
  );
}

/**
 * The API said nothing. This is not an empty answer and is never drawn as one:
 * a company that could not be read and a company with nothing in it are
 * different facts.
 */
export function Unreachable({
  detail,
  action,
}: {
  readonly detail: string;
  readonly action: string;
}): ReactElement {
  return (
    <div className="rounded-lg border border-unknown-line bg-unknown-bg p-4">
      <div className="flex items-start gap-2.5">
        <WifiOff className="mt-0.5 size-4 shrink-0 text-unknown" />
        <div className="min-w-0 flex-1">
          <p className="m-0 text-[13px] font-medium text-ink">ctower did not answer.</p>
          <Mono className="mt-1 block text-ink-2">{detail}</Mono>
          <p className="mt-1.5 mb-0 text-[12px] text-ink-2">{action}</p>
        </div>
        <Badge tone="unknown">unknown</Badge>
      </div>
    </div>
  );
}

/**
 * ctower answered, and the answer did not match the contract this client was
 * generated from. It is neither a refusal nor silence, and drawing it as either
 * would send an operator to the wrong place: this is a repository defect, not
 * an operational one.
 */
export function Malformed({ detail }: { readonly detail: string }): ReactElement {
  return (
    <div className="rounded-lg border border-warn-line bg-warn-bg p-4">
      <div className="flex items-start gap-2.5">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn" />
        <div className="min-w-0 flex-1">
          <p className="m-0 text-[13px] font-medium text-ink">
            ctower answered something this client cannot read.
          </p>
          <Mono className="mt-1 block break-all text-ink-2">{detail}</Mono>
          <p className="mt-1.5 mb-0 text-[12px] text-ink-2">
            The contract and the running API disagree. This one is for engineering.
          </p>
        </div>
        <Badge tone="warn">contract</Badge>
      </div>
    </div>
  );
}
