import { useState } from "react";
import { ChevronLeft, X } from "lucide-react";
import { Dialog } from "radix-ui";
import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { Button } from "../ui/primitives";
import { Inert } from "../projects/Inert";
import type { Authoring } from "../wizard/ceremony";
import { harnessChoices } from "./harnesses";
import type { HarnessFamily } from "./harnesses";
import { HarnessPicker } from "./HarnessPicker";
import { BLANK, documentWith, problemAt, problemsIn, recorded } from "./draft";
import type { Draft, Problem } from "./draft";

/**
 * Making an agent, in the two steps the operator asked for: choose the harness,
 * then say who this is.
 *
 * Two steps rather than one long form, because they are two different
 * questions. The first is a choice out of a closed set of cards and the second
 * is a description of a person, and putting a card grid at the top of a form
 * makes the choice look like a field.
 *
 * Nothing here can reach a refusal. The payload is derived and checked against
 * both authored schemas on every keystroke, the message lands under the field
 * that caused it, and `Create agent` does not act while anything is wrong — so
 * the review behind it never opens on a payload the record would answer
 * `bundle-schema-invalid` to.
 *
 * Most of what the reference console's form asks for, a ctower agent cannot
 * carry. A persona records a name and a pointer at its instructions; a profile
 * records the harness, the skills and the tools. There is nowhere to keep a
 * title, a reporting line, a trust level, a model, a thinking effort, a turn
 * limit or a heartbeat — so those are drawn, in place, as fields the record has
 * nowhere to keep. A box that takes an answer and drops it is worse than an
 * absence.
 */
export function NewAgent({
  authoring,
  company,
  open,
  onOpenChange,
}: {
  readonly authoring: Authoring;
  /** The company's name, for the trail at the top. */
  readonly company: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}): ReactElement {
  const [draft, setDraft] = useState<Draft>(BLANK);
  const [naming, setNaming] = useState(false);
  const [touched, setTouched] = useState(false);
  const problems = problemsIn(draft, authoring.tenant, recorded(authoring.recorded));
  const showing = touched || draft.name !== "" ? problems : [];

  const reset = (): void => {
    setDraft(BLANK);
    setNaming(false);
    setTouched(false);
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next): void => {
        if (!next) {
          reset();
        }
        onOpenChange(next);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[color-mix(in_srgb,var(--ink)_45%,transparent)]" />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed top-1/2 left-1/2 z-50 flex max-h-[86dvh] w-[min(760px,92vw)] flex-col",
            "-translate-x-1/2 -translate-y-1/2 rounded-md border border-line bg-card"
          )}
        >
          <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
            <span className="flex min-w-0 items-center gap-1.5 text-2xs text-muted">
              <span className="truncate">{company}</span>
              <span aria-hidden>›</span>
              <Dialog.Title className="m-0 truncate text-2xs font-normal text-fg">
                New agent
              </Dialog.Title>
            </span>
            <span className="flex-1" />
            <Dialog.Close asChild>
              <Button variant="quiet" size="sm" aria-label="Close">
                <X />
              </Button>
            </Dialog.Close>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            {naming ? (
              <Naming draft={draft} showing={showing} onDraft={setDraft} />
            ) : (
              <Choosing draft={draft} showing={showing} onDraft={setDraft} />
            )}
          </div>

          <footer className="flex flex-wrap items-center gap-2 border-t border-line px-6 py-3">
            {naming ? (
              <Button
                variant="quiet"
                size="sm"
                className="-ml-2.5"
                onClick={(): void => {
                  setNaming(false);
                }}
              >
                <ChevronLeft /> Harness
              </Button>
            ) : null}
            <span className="flex-1" />
            {naming ? (
              <>
                <Inert
                  className="chip"
                  reason="Starting an agent to try it needs the runner, which no browser can reach."
                >
                  Test agent
                </Inert>
                <Button
                  variant="primary"
                  onClick={(): void => {
                    setTouched(true);
                    if (problems.length === 0) {
                      authoring.propose(documentWith(authoring, draft));
                      // The pop-up closes onto the review it just opened, through
                      // the prop rather than its own handler, so the draft
                      // survives: an operator who reads the plan and comes back
                      // finds what they typed.
                      onOpenChange(false);
                    }
                  }}
                >
                  Create agent
                </Button>
              </>
            ) : (
              <Button
                variant="primary"
                disabled={draft.family === null}
                title={draft.family === null ? "Choose a harness first." : undefined}
                onClick={(): void => {
                  setNaming(true);
                }}
              >
                Next
              </Button>
            )}
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** Step one: the cards. */
function Choosing({
  draft,
  showing,
  onDraft,
}: {
  readonly draft: Draft;
  readonly showing: readonly Problem[];
  readonly onDraft: (draft: Draft) => void;
}): ReactElement {
  return (
    <>
      <h2 className="m-0 text-lg leading-tight font-semibold tracking-[-0.02em]">
        What does this agent run on?
      </h2>
      <p className="mt-1 mb-5 text-xs text-muted">
        The agent is created on the one you pick. You can add more later.
      </p>
      <HarnessPicker
        choices={harnessChoices()}
        value={draft.family}
        onChoose={(family: HarnessFamily): void => {
          onDraft({ ...draft, family });
        }}
      />
      <Inline message={problemAt(showing, "harness")} />
    </>
  );
}

/** Step two: who this is, and everything the record cannot yet be told. */
function Naming({
  draft,
  showing,
  onDraft,
}: {
  readonly draft: Draft;
  readonly showing: readonly Problem[];
  readonly onDraft: (draft: Draft) => void;
}): ReactElement {
  const chosen = harnessChoices().find((choice) => choice.family === draft.family);
  return (
    <>
      <input
        autoFocus
        value={draft.name}
        placeholder="Agent name"
        aria-label="Agent name"
        aria-invalid={problemAt(showing, "name") !== null}
        onChange={(event): void => {
          onDraft({ ...draft, name: event.target.value });
        }}
        className={cn(
          "w-full border-0 bg-transparent p-0 text-xl font-bold tracking-[-0.02em]",
          "text-fg outline-none placeholder:text-muted/70"
        )}
      />
      <Inline message={problemAt(showing, "name")} />

      {/* The choice from step one, named where the operator can see it while
          they answer step two. It is a real recorded fact about this agent, and
          the footer's own way back is how it is changed. */}
      {chosen === undefined ? null : (
        <p className="mt-2 mb-0 text-xs text-muted">On {chosen.name}</p>
      )}

      <Inert
        className="mt-2 block text-sm"
        reason="A recorded agent carries a name and the harness it runs on. There is nowhere to keep a job title or a reporting line yet."
      >
        Add a title and who it reports to…
      </Inert>

      <div className="mt-6 grid gap-5 sm:grid-cols-2">
        <Absent
          label="Trust"
          value="Standard"
          reason="How far an agent is trusted is granted per project on the Admin screen, and an agent carries no trust of its own."
        />
        <Absent
          label="Model"
          value="Default"
          reason="A recorded agent names no model. Which model ran is a fact of the run, recorded after it, not a setting on the agent."
        />
        <Absent
          label="Thinking effort"
          value="Default"
          reason="A recorded agent has nowhere to keep a thinking effort."
        />
        <Absent
          label="Max turns"
          value="Unlimited"
          reason="A recorded agent has nowhere to keep a turn limit."
        />
        <Absent
          label="Instructions"
          value="Written after it exists"
          reason="An agent's instructions are its own files, edited on its Instructions tab once it is recorded."
        />
        <Absent
          label="Heartbeat"
          value="Off"
          reason="A recorded agent has nowhere to keep a heartbeat, and nothing schedules one."
        />
        <Absent
          label="Environment"
          value="None"
          reason="Secrets are bound on the company, by reference and never by value, and an agent carries no environment of its own."
        />
        <Absent
          label="Skills"
          value="None"
          reason="An agent can hold the company's skills. Choosing them is the agent's own Skills tab, not this screen."
        />
      </div>
    </>
  );
}

/**
 * A field the reference console has and the record has nowhere to keep.
 *
 * It shows what the agent will actually behave as, so the operator learns the
 * setting exists and what it is fixed at — and the reason it cannot be moved
 * sits on the label, reachable by keyboard, per the copy budget's rule that
 * rationale is never rendered by default.
 */
function Absent({
  label,
  value,
  reason,
}: {
  readonly label: string;
  readonly value: string;
  readonly reason: string;
}): ReactElement {
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="text-2xs text-muted">{label}</span>
        <Inert className="text-2xs" reason={reason}>
          not recorded
        </Inert>
      </div>
      <Inert
        className="flex h-9 items-center rounded-sm border border-line px-3 text-sm"
        reason={reason}
      >
        {value}
      </Inert>
    </div>
  );
}

/** The message the record would have refused with, under the field that caused it. */
function Inline({ message }: { readonly message: string | null }): ReactElement | null {
  return message === null ? null : (
    <p role="alert" className="mt-1.5 mb-0 text-xs text-danger">
      {message}
    </p>
  );
}
