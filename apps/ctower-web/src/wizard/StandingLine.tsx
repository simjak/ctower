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
 * and a fact belongs on one line: valid, how many checks passed, whether
 * anything would move, and the digest it is all about. Walking an operator
 * through four screens to arrive at "nothing happened" is ritual, and ritual is
 * the opposite of everything here being real.
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
    <>
      {standing.validation.valid ? (
        <Chip tone="ok">valid</Chip>
      ) : (
        <Chip tone="danger">not valid</Chip>
      )}
      <Chip>
        {passed} of {checks.length} checks
      </Chip>
      {moved === 0 ? <Chip>no changes</Chip> : <Chip tone="amber">{moved} would move</Chip>}
      {digest === null ? null : (
        <Mono className="text-muted" title={digest}>
          {shortDigest(digest)}
        </Mono>
      )}
    </>
  );
}
