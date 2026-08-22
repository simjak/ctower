import type { ReactElement } from "react";
import type { Problem } from "@ctower/client";
import { Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";

/** A call is out. The CLI's own working mark, and no spinner of our own. */
export function Asking({ what }: { readonly what: string }): ReactElement {
  return (
    <p className="m-0 flex items-center gap-2 py-6 text-sm text-muted">
      <Mark name="working" />
      {what}
    </p>
  );
}

/**
 * The API answered, and the answer was no.
 *
 * Fact, then the one next action, then the registry's own code. The wizard
 * never restates a refusal in its own words — the registry's words are the ones
 * the operator will meet again in the log and in the CLI — and the code sits on
 * its own line rather than competing with the sentence for width.
 */
export function Refused({
  problem,
  action,
}: {
  readonly problem: Problem;
  readonly action: string;
}): ReactElement {
  return (
    <Block mark="dead" tone="danger">
      <p className="m-0 text-sm font-medium text-fg">{problem.detail}</p>
      {problem.unmet_facts !== undefined && problem.unmet_facts.length > 0 ? (
        <ul className="mt-2 mb-0 list-none space-y-0.5 p-0">
          {problem.unmet_facts.map((fact) => (
            <li key={fact}>
              <Mono className="text-muted">{fact}</Mono>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-1.5 mb-0 text-xs text-muted">{action}</p>
      <Mono className="mt-2 block text-danger">{problem.code}</Mono>
    </Block>
  );
}

/**
 * The API said nothing.
 *
 * There is deliberately no mark on this one. A state with no recorded fact
 * draws nothing at all, because borrowing a neighbour’s glyph is how a read
 * that never answered gets rendered as a state that did.
 */
export function Unreachable({
  detail,
  action,
}: {
  readonly detail: string;
  readonly action: string;
}): ReactElement {
  return (
    <Block mark={null} tone="muted">
      <p className="m-0 text-sm font-medium text-fg">ctower did not answer.</p>
      <Mono className="mt-1 block text-muted">{detail}</Mono>
      <p className="mt-1.5 mb-0 text-xs text-muted">{action}</p>
    </Block>
  );
}

/**
 * ctower answered, and the answer did not match the contract this client was
 * generated from. Neither a refusal nor silence, and drawing it as either would
 * send an operator to the wrong place: this one is a repository defect.
 */
export function Malformed({ detail }: { readonly detail: string }): ReactElement {
  return (
    <Block mark="warn" tone="amber">
      <p className="m-0 text-sm font-medium text-fg">
        ctower answered something this client cannot read.
      </p>
      <Mono className="mt-1 block break-all text-muted">{detail}</Mono>
      <p className="mt-1.5 mb-0 text-xs text-muted">
        The contract and the running API disagree. This one is for engineering.
      </p>
    </Block>
  );
}

const EDGE = {
  danger: "border-danger/40 bg-danger/8",
  amber: "border-amber/40 bg-amber/10",
  muted: "border-line bg-raised",
} as const;

function Block({
  mark,
  tone,
  children,
}: {
  readonly mark: "dead" | "warn" | null;
  readonly tone: keyof typeof EDGE;
  readonly children: ReactElement | readonly (ReactElement | null)[];
}): ReactElement {
  return (
    <div className={`rounded-md border p-3 ${EDGE[tone]}`}>
      <div className="flex items-start gap-2">
        {mark === null ? null : <Mark name={mark} className="mt-0.5" />}
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
