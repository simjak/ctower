import { Check } from "lucide-react";
import type { ReactElement } from "react";
import type { Answer } from "../api/client";
import { Chip, Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { Malformed, Refused, Unreachable } from "../wizard/states";
import { ADAPTERS } from "./answers";
import type { Answers } from "./answers";
import { StepFrame } from "./StepFrame";

/**
 * Step 5 — what is about to be recorded, and the one command that records it.
 *
 * The checklist is the four answers, ticked because they were given and not
 * because anything succeeded yet. Nothing here claims the company exists: the
 * tick beside `Mission` is absent when it was skipped, and the whole list is
 * still just an intention until `Get started` comes back accepted.
 */
export function ReviewStep({
  answers,
  outcome,
  previewing,
  onStart,
  onBack,
}: {
  readonly answers: Answers;
  readonly outcome: Answer<unknown> | null;
  readonly previewing: boolean;
  readonly onStart: () => void;
  readonly onBack: () => void;
}): ReactElement {
  const adapter = ADAPTERS.find((entry) => entry.key === answers.adapter);
  const sending = outcome?.kind === "asking";

  return (
    <StepFrame
      step={5}
      total={5}
      icon={<Check className="size-5" />}
      title="Review"
      lead="This is what gets recorded, in one command."
      onBack={onBack}
      onNext={onStart}
      nextLabel={sending ? "Checking" : previewing ? "Check and plan" : "Get started"}
      nextReady={!sending}
    >
      <ul className="m-0 list-none space-y-3 p-0">
        <Line label="Organization" value={answers.name} note={answers.key} given />
        <Line label="Harness" value={adapter?.label ?? answers.adapter} given />
        <Line label="Agent" value={answers.agentName} note={`on ${adapter?.label ?? ""}`} given />
        <Line
          label="Mission"
          value={answers.mission === "" ? "Not set" : answers.mission}
          given={answers.mission !== ""}
        />
      </ul>

      {outcome !== null && outcome.kind === "answered" && previewing ? (
        <p className="mt-6 mb-0 rounded-md border border-line bg-card p-4 text-sm text-muted">
          Checked and planned against the live registry. A preview does not write — on a tower that
          already has a company this command would replace its whole definition.
        </p>
      ) : null}
      {outcome === null || outcome.kind === "asking" || outcome.kind === "answered" ? null : (
        <div className="mt-6">
          <Outcome outcome={outcome} />
        </div>
      )}
    </StepFrame>
  );
}

function Outcome({ outcome }: { readonly outcome: Answer<unknown> }): ReactElement | null {
  switch (outcome.kind) {
    case "refused":
      return (
        <Refused
          problem={outcome.problem}
          action="Nothing was created. Go back and change what it refused."
        />
      );
    case "unreachable":
      return <Unreachable detail={outcome.detail} action="Nothing was created. Try again." />;
    case "malformed":
      return <Malformed detail={outcome.detail} />;
    case "asking":
    case "answered":
      return null;
  }
}

function Line({
  label,
  value,
  note,
  given,
}: {
  readonly label: string;
  readonly value: string;
  readonly note?: string;
  readonly given: boolean;
}): ReactElement {
  return (
    <li className="flex items-baseline gap-3">
      {given ? <Mark name="done" /> : <span aria-hidden className="mono w-[1.4em] shrink-0" />}
      <span className="w-28 shrink-0 text-xs text-muted">{label}</span>
      <span className={given ? "min-w-0 text-sm text-fg" : "min-w-0 text-sm text-muted"}>
        {value}
      </span>
      {note === undefined || note.trim() === "on" ? null : (
        <Mono className="text-muted">{note}</Mono>
      )}
      {given ? null : <Chip>skipped</Chip>}
    </li>
  );
}
