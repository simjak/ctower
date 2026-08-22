import { Check } from "lucide-react";
import type { ReactElement } from "react";
import type { CompanyBundleCommandResult } from "@ctower/client";
import { Chip, Mono } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { Asking, Malformed, Refused, Unreachable } from "../wizard/states";
import { adapterFor } from "../harness/schema";
import type { Answers } from "./answers";
import type { FirstRunOutcome } from "./outcome";
import { commandKeySurvivesReload } from "../api/commandKey";
import { StepFrame } from "./StepFrame";

/**
 * Step 5 — what is about to be recorded, and the one command that records it.
 *
 * The checklist carries the idle mark, never the done mark: nothing here has
 * been recorded, and a state with no recorded fact never borrows the glyph of
 * one that has. A skipped answer carries no mark at all.
 *
 * What comes back is rendered as what it is. The API returns the same result
 * shape for an accepted command and one that is merely durable-pending, and
 * only one of those created a company.
 */
export function ReviewStep({
  answers,
  applied,
  previewing,
  onStart,
  onBack,
}: {
  readonly answers: Answers;
  readonly applied: FirstRunOutcome | null;
  readonly previewing: boolean;
  readonly onStart: () => void;
  readonly onBack: () => void;
}): ReactElement {
  const adapter = adapterFor(answers.adapter);
  const sending = applied?.kind === "asking";
  // Only acceptance is final. A refusal, an unreachable tower, an unreadable
  // answer, a preview, and a command taken but not yet durable may all be tried
  // again — and the same command key makes that the same command rather than a
  // second one.
  const created = applied?.kind === "answered" && applied.value.durability_state === "accepted";

  return (
    <StepFrame
      step={5}
      total={5}
      icon={<Check className="size-5" />}
      title="Review"
      lead="This is what gets recorded, in one command."
      onBack={onBack}
      busy={sending}
      onNext={onStart}
      nextLabel={retryLabel(applied, previewing)}
      nextReady={!created}
    >
      <ul className="m-0 list-none space-y-3 p-0">
        <Line label="Organization" value={answers.name} note={answers.key} given />
        <Line label="Harness" value={adapter?.label ?? answers.adapter} given />
        <Line label="Agent" value={answers.agentName} given />
        <Line
          label="Mission"
          value={answers.mission === "" ? "Not set" : answers.mission}
          given={answers.mission !== ""}
        />
      </ul>

      {applied === null ? null : (
        <div className="mt-6">
          <Outcome applied={applied} />
        </div>
      )}
    </StepFrame>
  );
}

function Outcome({ applied }: { readonly applied: FirstRunOutcome }): ReactElement | null {
  switch (applied.kind) {
    case "asking":
      return <Asking what="Creating this company" />;
    case "previewed":
      return (
        <p className="m-0 rounded-md border border-line bg-card p-4 text-sm text-muted">
          Checked and planned against the live registry. A preview does not write — on a tower that
          already has a company this command would replace its whole definition.
        </p>
      );
    case "refused":
      return (
        <Refused
          problem={applied.problem}
          action="Nothing was created. Go back and change what it refused."
        />
      );
    case "unreachable":
      return (
        <Unreachable
          detail={applied.detail}
          action="Whether anything was written is not known. Creating again reuses the same command, so it cannot write twice."
        />
      );
    case "malformed":
      return <Malformed detail={applied.detail} />;
    case "answered":
      return <Receipt receipt={applied.value} />;
  }
}

/**
 * The one thing this may not do is call a pending write done. The authored API
 * answers `durability_pending` in the same shape as an acceptance, and only the
 * accepted one created a company.
 */
function Receipt({ receipt }: { readonly receipt: CompanyBundleCommandResult }): ReactElement {
  if (receipt.durability_state === "accepted") {
    return (
      <p className="m-0 flex items-center gap-2 text-sm text-fg">
        <Mark name="done" /> Created — now at version <Mono>{receipt.active_version}</Mono>.
      </p>
    );
  }
  return (
    <div className="rounded-md border border-amber/40 bg-amber/10 p-4">
      <div className="flex items-start gap-2">
        <Mark name="warn" className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="m-0 text-sm font-medium text-fg">
            ctower took the command and has not confirmed it is durable.
          </p>
          <p className="mt-1.5 mb-0 text-xs text-muted">
            The company is not created until it says so. Creating again reuses the same command
            {commandKeySurvivesReload() ? "" : ", though not across a reload on this browser"}.
          </p>
          <Mono className="mt-2 block text-muted">{receipt.command_id}</Mono>
        </div>
      </div>
    </div>
  );
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
      {given ? <Mark name="idle" /> : <span aria-hidden className="mono w-[1.4em] shrink-0" />}
      <span className="w-28 shrink-0 text-xs text-muted">{label}</span>
      <span className={given ? "min-w-0 text-sm text-fg" : "min-w-0 text-sm text-muted"}>
        {value}
      </span>
      {note === undefined ? null : <Mono className="text-muted">{note}</Mono>}
      {given ? null : <Chip>skipped</Chip>}
    </li>
  );
}

/**
 * The button says what pressing it does now. After something that did not
 * record, that is a second try of the same command — never a new one.
 */
function retryLabel(applied: FirstRunOutcome | null, previewing: boolean): string {
  if (applied?.kind === "asking") {
    return "Working";
  }
  if (previewing) {
    return applied === null ? "Check and plan" : "Check again";
  }
  if (applied === null) {
    return "Get started";
  }
  if (applied.kind === "answered" && applied.value.durability_state === "accepted") {
    return "Get started";
  }
  return "Send it again";
}
