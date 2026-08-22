import { Bot, Building2, Cpu, Target } from "lucide-react";
import type { ReactElement } from "react";
import { Button, Chip, Input } from "../ui/primitives";
import { cn } from "../ui/cn";
import { CheckList } from "../harness/CheckList";
import { ConfigFields } from "../harness/ConfigFields";
import { Field } from "../ui/form";
import { ADAPTERS, adapterFor } from "../harness/schema";
import { suggestKey } from "./answers";
import type { Answers } from "./answers";
import { StepFrame } from "./StepFrame";
import { Refused } from "../wizard/states";
import type { Answer } from "../api/client";

interface StepProps {
  readonly answers: Answers;
  readonly onAnswers: (answers: Answers) => void;
  readonly onNext: () => void;
  readonly onBack?: (() => void) | undefined;
  /**
   * Something the operator started is still in flight. Every control that could
   * change the draft or leave the step goes inert until it settles, so no answer
   * can arrive for a question that has since been edited.
   */
  readonly busy: boolean;
}

const TOTAL = 5;

/** Step 1 — what this organization is called. */
export function NameStep({
  answers,
  onAnswers,
  onNext,
  busy,
  keyCheck,
}: StepProps & { readonly keyCheck: Answer<unknown> | null }): ReactElement {
  const checking = keyCheck?.kind === "asking";
  return (
    <StepFrame
      step={1}
      total={TOTAL}
      icon={<Building2 className="size-5" />}
      title="Name your organization"
      lead="What should we call your team or company?"
      onNext={onNext}
      busy={busy}
      nextLabel={checking ? "Checking" : "Next"}
      nextReady={answers.name.trim().length > 0 && answers.key.trim().length > 2}
    >
      <Label htmlFor="org-name">Name</Label>
      <Input
        id="org-name"
        className="h-11 text-md"
        disabled={busy}
        value={answers.name}
        placeholder="Acme Corp"
        onChange={(event): void => {
          const name = event.target.value;
          onAnswers({
            ...answers,
            name,
            key: answers.key === suggestKey(answers.name) ? suggestKey(name) : answers.key,
          });
        }}
      />
      <Label htmlFor="org-key">Key</Label>
      <Input
        id="org-key"
        className="h-11 font-mono text-sm"
        disabled={busy}
        value={answers.key}
        placeholder="acme-corp"
        spellCheck={false}
        onChange={(event): void => {
          onAnswers({ ...answers, key: event.target.value });
        }}
      />
      <p className="mt-2 mb-0 text-xs text-muted">
        It must match the key this tower is registered under.
      </p>
      {keyCheck !== null && keyCheck.kind === "refused" ? (
        <div className="mt-4">
          <Refused
            problem={keyCheck.problem}
            action="Change the key to the one this tower is registered under, then continue."
          />
        </div>
      ) : null}
    </StepFrame>
  );
}

/** Step 2 — the runtime the team runs on, chosen before the staff. */
export function HarnessStep({ answers, onAnswers, onNext, onBack, busy }: StepProps): ReactElement {
  const adapter = adapterFor(answers.adapter);
  return (
    <StepFrame
      step={2}
      total={TOTAL}
      icon={<Cpu className="size-5" />}
      title="Connect harness adapters"
      lead="Pick the runtime your team runs on. Your first agent is created on it."
      onBack={onBack}
      onNext={onNext}
      busy={busy}
      nextLabel="Connect"
      nextReady={adapter !== undefined}
      /* The lifted test button: this step owns the control, the harness form
         owns what it means. Today it owns a refusal, because the probe has no
         operation behind it yet. */
      action={
        <Button variant="ghost" size="sm" disabled title="The harness surface has not landed yet.">
          Test now
        </Button>
      }
    >
      <p className="mb-1.5 text-xs text-muted">Adapter</p>
      <div className="grid gap-3 sm:grid-cols-3">
        {ADAPTERS.map((entry) => (
          <button
            key={entry.key}
            type="button"
            disabled={busy}
            aria-pressed={answers.adapter === entry.key}
            onClick={(): void => {
              onAnswers({ ...answers, adapter: entry.key });
            }}
            className={cn(
              "cursor-pointer rounded-md border px-4 py-4 text-center",
              answers.adapter === entry.key
                ? "border-amber bg-amber/10"
                : "border-line bg-card hover:bg-raised"
            )}
          >
            <span className="block text-sm font-semibold text-fg">{entry.label}</span>
            <span className="mt-1 block text-xs text-muted">{entry.blurb}</span>
          </button>
        ))}
      </div>

      <div className="mt-5">
        <p className="mb-1.5 text-xs text-muted">Settings</p>
        <ConfigFields
          fields={adapter?.config ?? []}
          values={{}}
          onValue={(): void => {
            /* no adapter declares a field yet; the renderer is what will draw them */
          }}
          empty="This adapter declares no settings yet."
        />
      </div>

      <div className="mt-5">
        <CheckList
          title="Adapter environment check"
          checks={[]}
          empty={
            <p className="m-0 text-sm text-muted">
              A live probe that asks the adapter to answer for itself.{" "}
              <span className="text-fg">Available when the harness surface lands.</span>
            </p>
          }
        />
      </div>
    </StepFrame>
  );
}

/** Step 3 — the first agent, created on the harness chosen in step 2. */
export function AgentStep({ answers, onAnswers, onNext, onBack, busy }: StepProps): ReactElement {
  const adapter = adapterFor(answers.adapter);
  return (
    <StepFrame
      step={3}
      total={TOTAL}
      icon={<Bot className="size-5" />}
      title="Create your first agent"
      lead={
        <>
          They will drive <b className="font-semibold text-fg">{answers.name}</b>. We default to{" "}
          <b className="font-semibold text-fg">Commander</b>. Rename it to anything you like.
        </>
      }
      onBack={onBack}
      onNext={onNext}
      busy={busy}
      nextLabel="Next"
      nextReady={answers.agentName.trim().length > 0}
    >
      <div className="mb-6 flex items-center justify-center gap-3 rounded-md border border-line bg-card px-4 py-5">
        <span className="text-sm font-semibold text-fg">{answers.agentName.trim() || "…"}</span>
        <span aria-hidden className="text-muted">
          on
        </span>
        <Chip tone="amber">{adapter?.label ?? answers.adapter}</Chip>
      </div>
      <Label htmlFor="agent-name">Name</Label>
      <Input
        id="agent-name"
        className="h-11 text-md"
        disabled={busy}
        value={answers.agentName}
        onChange={(event): void => {
          onAnswers({ ...answers, agentName: event.target.value });
        }}
      />
    </StepFrame>
  );
}

const SUGGESTIONS: readonly { readonly mission: string; readonly criterion: string }[] = [
  {
    mission: "Ship a trustworthy product every week.",
    criterion: "Every release is attributable and supported by current proof.",
  },
  {
    mission: "Keep the delivery pipeline green and fast.",
    criterion: "No change sits unreviewed for more than a day.",
  },
  {
    mission: "Turn research into shipped features.",
    criterion: "Every experiment ends in a decision that is written down.",
  },
];

/** Step 4 — the mission, on one screen, and skippable. */
export function MissionStep({
  answers,
  onAnswers,
  onNext,
  onBack,
  onSkip,
  busy,
}: StepProps & { readonly onSkip: () => void }): ReactElement {
  return (
    <StepFrame
      step={4}
      total={TOTAL}
      icon={<Target className="size-5" />}
      title="Define your mission"
      lead={
        <>
          It guides the work <b className="font-semibold text-fg">{answers.name}</b> takes on. You
          can add it later instead.
        </>
      }
      onBack={onBack}
      onNext={onNext}
      busy={busy}
      nextLabel="Confirm mission"
      nextReady={answers.mission.trim().length > 0}
      onSkip={onSkip}
      skipLabel="Skip for now"
    >
      <Label htmlFor="mission">Mission</Label>
      <Input
        id="mission"
        className="h-11 text-md"
        disabled={busy}
        value={answers.mission}
        placeholder="What is your team trying to achieve?"
        onChange={(event): void => {
          onAnswers({ ...answers, mission: event.target.value });
        }}
      />
      <div className="mt-3 flex flex-wrap gap-2">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion.mission}
            type="button"
            disabled={busy}
            className="chip cursor-pointer hover:bg-raised disabled:opacity-55"
            onClick={(): void => {
              onAnswers({
                ...answers,
                mission: suggestion.mission,
                criterion: suggestion.criterion,
              });
            }}
          >
            {suggestion.mission}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {/* D9: the reason a criterion is mandatory is rationale, so it sits
            behind the one-line disclosure rather than on the screen. */}
        <Field
          label="How you will know it worked"
          hint="The goal document this writes requires exactly one success criterion."
        >
          <Input
            id="criterion"
            className="h-11 text-sm"
            disabled={busy}
            value={answers.criterion}
            placeholder="One thing that proves it."
            onChange={(event): void => {
              onAnswers({ ...answers, criterion: event.target.value });
            }}
          />
        </Field>
      </div>
    </StepFrame>
  );
}

function Label({
  htmlFor,
  children,
}: {
  readonly htmlFor: string;
  readonly children: string;
}): ReactElement {
  return (
    <label className="mt-4 mb-1.5 block text-xs text-muted" htmlFor={htmlFor}>
      {children}
    </label>
  );
}
