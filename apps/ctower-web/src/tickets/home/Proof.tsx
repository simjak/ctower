import type { ReactElement } from "react";
import type { AuditEvent } from "@ctower/client";
import { clockWords, whenWords } from "../words";
import { Absent, Fact, Section } from "./parts";

type ProofEvent = Extract<AuditEvent, { readonly kind: "proof.changed" }>;

/**
 * What this ticket has to prove, as far as the record will say.
 *
 * The proof events answer that criteria were frozen and when, how many pieces
 * of evidence were shown and when the last one landed, and whether a verdict
 * has been recorded. They do **not** answer what the criteria say:
 * `ProofChangedAuditPayload` carries an operation, a version and a digest, and
 * no declared read returns the criteria themselves. So the counts and the times
 * are drawn, and the one thing that is missing is said in a line rather than
 * guessed at from a title or a stage.
 */
export function Proof({
  events,
  now,
}: {
  readonly events: readonly AuditEvent[];
  readonly now: number;
}): ReactElement {
  const proofs = events.filter(isProof);
  const frozen = proofs.find((event) => event.payload.operation === "freeze_criteria") ?? null;
  const shown = proofs.filter((event) => event.payload.operation === "record_evidence");
  const judged = proofs.filter((event) => event.payload.operation === "record_verdict");
  const lastShown = shown.at(-1);
  const lastJudged = judged.at(-1);

  if (frozen === null && shown.length === 0) {
    return (
      <Section title="What it has to prove">
        <Absent>Nothing has been agreed on this ticket yet, and nothing has been shown.</Absent>
      </Section>
    );
  }

  return (
    <Section
      title="What it has to prove"
      note={frozen === null ? null : `Agreed ${whenWords(frozen.occurred_at, now)}`}
    >
      <Fact label="Agreed">
        {frozen === null
          ? "Nothing has been agreed yet."
          : `Settled at ${clockWords(frozen.occurred_at)}, and unchanged since.`}
      </Fact>
      <Fact label="Shown so far">
        {lastShown === undefined
          ? "Nothing yet."
          : `${count(shown.length, "piece", "pieces")}, the last at ${clockWords(lastShown.occurred_at)}.`}
      </Fact>
      <Fact label="Judged">
        {lastJudged === undefined
          ? "No verdict has been recorded."
          : `${count(judged.length, "verdict", "verdicts")}, the last ${whenWords(lastJudged.occurred_at, now)}.`}
      </Fact>
      <Absent>What was agreed is not written anywhere this screen can read.</Absent>
    </Section>
  );
}

function count(many: number, one: string, more: string): string {
  return `${String(many)} ${many === 1 ? one : more}`;
}

function isProof(event: AuditEvent): event is ProofEvent {
  return event.kind === "proof.changed";
}
