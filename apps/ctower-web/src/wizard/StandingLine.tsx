import { ChevronDown } from "lucide-react";
import type { ReactElement } from "react";
import type { Answer } from "../api/client";
import { Chip, Mono } from "../ui/primitives";
import { shortDigest } from "./bundle";
import { movedCount } from "./review/actions";
import type { Standing } from "./standing";

/**
 * Where the four-step ceremony went.
 *
 * Checking and planning an unchanged definition is not a journey, it is a fact,
 * and a fact does not need a screen. It does not need the header either: an
 * operator opening this page is going to change something, and `valid`, `5 of 5
 * checks`, `no changes` and a digest are four answers to a question nobody
 * asked. They are one word away instead — the digest is the record's own
 * identity and stays reachable, per D9, behind an affordance rather than
 * rendered by default.
 *
 * A standing that is not settled keeps its chip. Checking, refused, and
 * unreachable are states an operator has to act on, and a state that needs
 * acting on is never folded away.
 *
 * Once the draft is edited these facts are about a document that no longer
 * exists, so they are replaced by what is true instead: how many edits stand,
 * and that nothing has been checked yet.
 */
export function StandingLine({
  standing,
  edits,
  digest,
}: {
  readonly standing: Answer<Standing>;
  readonly edits: number;
  readonly digest: string | null;
}): ReactElement {
  if (edits > 0) {
    return (
      <>
        <Chip tone="amber">
          {edits} {edits === 1 ? "edit" : "edits"}
        </Chip>
        <Chip>not checked</Chip>
      </>
    );
  }

  switch (standing.kind) {
    case "asking":
      return <Chip>checking</Chip>;
    case "refused":
      return <Chip tone="danger">{standing.problem.code}</Chip>;
    case "unreachable":
      return <Chip>not checked</Chip>;
    case "malformed":
      return <Chip tone="amber">contract</Chip>;
    case "answered":
      return <Recorded standing={standing.value} digest={digest} />;
  }
}

/**
 * What was recorded, one press away, and named for who presses it.
 *
 * The digest is the record's identity and the one thing on this page that is
 * addressed to a machine, so the affordance says `Developer details` rather than
 * something friendlier: an operator who never opens it never meets a hash, and
 * the person who needs one knows exactly where it went.
 *
 * `details` is the disclosure this codebase already uses for a fold nobody has
 * to open — the plan's unchanged rows use the same one — so the keyboard, the
 * screen reader and the Escape key are the platform's rather than this file's.
 */
function Recorded({
  standing,
  digest,
}: {
  readonly standing: Standing;
  readonly digest: string | null;
}): ReactElement {
  const checks = standing.validation.checks;
  const passed = checks.filter((check) => check.status === "passed").length;
  const moved = movedCount(standing.plan.actions);

  return (
    <details className="relative">
      <summary className="chip cursor-pointer list-none hover:bg-raised">
        Developer details
        <ChevronDown aria-hidden className="size-3" />
      </summary>
      <div className="absolute right-0 z-30 mt-1.5 flex w-max flex-col items-end gap-2 rounded-md border border-line bg-card p-3">
        <div className="flex items-center gap-2">
          {standing.validation.valid ? (
            <Chip tone="ok">valid</Chip>
          ) : (
            <Chip tone="danger">not valid</Chip>
          )}
          <Chip>
            {passed} of {checks.length} checks
          </Chip>
          {moved === 0 ? <Chip>no changes</Chip> : <Chip tone="amber">{moved} would move</Chip>}
        </div>
        {digest === null ? null : (
          <Mono className="text-muted" title={digest}>
            {shortDigest(digest)}
          </Mono>
        )}
      </div>
    </details>
  );
}
