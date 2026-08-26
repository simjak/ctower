import { useState } from "react";
import { Maximize2, Minimize2, X } from "lucide-react";
import { Dialog } from "radix-ui";
import type { ReactElement, ReactNode } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { resourceOf } from "../mint/component";
import { cn } from "../ui/cn";
import { Hint } from "../ui/form";
import { Button, Input } from "../ui/primitives";
import type { Authoring } from "../wizard/ceremony";
import { BLANK, payloadOf, problemAt, problemsIn } from "./draft";
import type { Draft } from "./draft";
import { PROJECT_SCHEMA_REF, REQUIRED } from "./schema";
import { Inert } from "./Inert";

/**
 * Making a project, in the pop-up the operator asked for.
 *
 * A document rather than a form: the name is the heading you would type on a
 * blank page, and what the record needs beyond it — the key it is stored under,
 * the prefix its tickets carry, the goal it serves — is derived or supplied
 * rather than asked. Creating a project is naming a project.
 *
 * Nothing here can reach a refusal. The payload is checked against the authored
 * contract on every keystroke, the message lands under the field that caused it,
 * and `Create project` does not act while anything is wrong — so the review
 * behind it is never opened on a payload the record would answer
 * `bundle-schema-invalid` to. That dead page stays where it belongs: over a
 * refusal the server actually made.
 */
export function NewProject({
  authoring,
  goals,
  company,
  open,
  onOpenChange,
}: {
  readonly authoring: Authoring;
  /** The goals this company records; a project is given the first of them. */
  readonly goals: readonly string[];
  /** The company's name, for the trail at the top. */
  readonly company: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}): ReactElement {
  const [draft, setDraft] = useState<Draft>(BLANK);
  const [wide, setWide] = useState(false);
  const [touched, setTouched] = useState(false);
  const problems = problemsIn(draft, recordedKeys(authoring.recorded));
  // A blank form is not a form full of mistakes. The messages appear once the
  // operator has typed, and on the press that would have submitted.
  const showing = touched || draft.name !== "" ? problems : [];

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next): void => {
        if (!next) {
          setDraft(BLANK);
          setTouched(false);
        }
        onOpenChange(next);
      }}
    >
      <Dialog.Portal>
        {/* The same scrim the ticket panel draws, at the weight a modal earns.
            `--ink` is the one token that is the same colour in both themes, so
            the dimming is dimming in both rather than an inversion in one. */}
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[color-mix(in_srgb,var(--ink)_45%,transparent)]" />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed top-1/2 left-1/2 z-50 flex -translate-x-1/2 -translate-y-1/2 flex-col",
            "rounded-md border border-line bg-card",
            wide ? "h-[86dvh] w-[min(1080px,92vw)]" : "w-[min(680px,92vw)]"
          )}
        >
          <header className="flex items-center gap-2 border-b border-line px-4 py-2.5">
            <span className="flex min-w-0 items-center gap-1.5 text-2xs text-muted">
              <span className="truncate">{company}</span>
              <span aria-hidden>›</span>
              <Dialog.Title className="m-0 truncate text-2xs font-normal text-fg">
                New project
              </Dialog.Title>
            </span>
            <span className="flex-1" />
            <Button
              variant="quiet"
              size="sm"
              aria-label={wide ? "Shrink" : "Expand"}
              onClick={(): void => {
                setWide(!wide);
              }}
            >
              {wide ? <Minimize2 /> : <Maximize2 />}
            </Button>
            <Dialog.Close asChild>
              <Button variant="quiet" size="sm" aria-label="Close">
                <X />
              </Button>
            </Dialog.Close>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            <input
              autoFocus
              value={draft.name}
              placeholder="Project name"
              aria-label="Project name"
              aria-invalid={problemAt(showing, "name") !== null}
              onChange={(event): void => {
                setDraft({ ...draft, name: event.target.value });
              }}
              className={cn(
                "w-full border-0 bg-transparent p-0 text-xl font-bold tracking-[-0.02em]",
                "text-fg outline-none placeholder:text-muted/70"
              )}
            />
            <Inline message={problemAt(showing, "name")} />

            {/* The line the reference puts under the heading. A project payload
                is a closed shape — six fields, and no room for prose — so this
                says what it is instead of taking words the record would drop. */}
            <Inert
              className="mt-2 block text-sm"
              reason="A recorded project carries a name, a repository and the goal it serves. There is nowhere to keep a description yet."
            >
              Add description…
            </Inert>

            <div className="mt-6 space-y-5">
              <Labelled
                label="Repo URL"
                note={REPOSITORY_IS_REQUIRED ? "required" : "optional"}
                why={REPOSITORY_IS_REQUIRED ? REPOSITORY_REASON : undefined}
              >
                <Input
                  value={draft.repoUrl}
                  placeholder="https://github.com/org/repo"
                  spellCheck={false}
                  aria-invalid={problemAt(showing, "repoUrl") !== null}
                  onChange={(event): void => {
                    setDraft({ ...draft, repoUrl: event.target.value });
                  }}
                />
                <Inline message={problemAt(showing, "repoUrl")} />
              </Labelled>

              <Labelled label="Local folder" note="optional">
                <div className="flex items-center gap-2">
                  <Inert
                    className="flex h-9 flex-1 items-center rounded-sm border border-line px-3 text-sm"
                    reason="A recorded project has no local folder, and a browser cannot read one."
                  >
                    Not set
                  </Inert>
                  <Inert
                    className="flex h-9 items-center rounded-sm border border-line px-3 text-sm font-semibold"
                    reason="A recorded project has no local folder, and a browser cannot read one."
                  >
                    Choose
                  </Inert>
                </div>
              </Labelled>
            </div>
          </div>

          <footer className="flex flex-wrap items-center gap-2 border-t border-line px-6 py-3">
            <Inert className="chip" reason="A recorded project holds no status.">
              planned
            </Inert>
            <Inert
              className="chip"
              reason="This project serves the goals this company records. Choosing among them is the project's own screen, not this one."
            >
              Goal
            </Inert>
            <Inert className="chip" reason="A recorded project holds no due date.">
              Due date
            </Inert>
            <span className="flex-1" />
            <Button
              variant="primary"
              disabled={goals.length === 0}
              title={goals.length === 0 ? "This company records no goal to serve yet." : undefined}
              onClick={(): void => {
                setTouched(true);
                if (problems.length === 0 && goals.length > 0) {
                  authoring.propose(withProject(authoring, draft, goals));
                  // The pop-up closes onto the review it just opened. It closes
                  // through the prop rather than the dialog's own handler, so
                  // the draft survives: an operator who reads the plan and comes
                  // back finds what they typed, not a blank page.
                  onOpenChange(false);
                }
              }}
            >
              Create project
            </Button>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/**
 * Whether the record still insists a project name a repository.
 *
 * Read from the contract rather than written down, so the word under the field
 * is the same fact the validator enforces. The day `repository_ref` leaves the
 * schema's required list, this field says `optional` and asks nothing further —
 * the copy cannot outlive the rule it describes.
 */
const REPOSITORY_IS_REQUIRED = REQUIRED.includes("repository_ref");

/**
 * Why a project that is not software still has to name a repository.
 *
 * The operator asked exactly that, and the honest answer is that this is the
 * record's shape and not a judgement about his project: a project payload is
 * six fields and one of them is the repository. Saying so is the whole fix
 * available on this screen — making the field genuinely optional is a change to
 * the project component contract, not to a form.
 */
const REPOSITORY_REASON =
  "A recorded project names one repository, whatever kind of work it does. There is nowhere to keep a project without one yet.";

/**
 * A field with its label, the reference's own optional/required note, and — when
 * the note would otherwise be a demand nobody explained — the reason behind it.
 *
 * D9 keeps rationale off the screen and reachable on the control, so the reason
 * opens on hover and on focus rather than sitting under the field as a
 * paragraph. A note that says `required` and nothing else is the console giving
 * an order; a note a person can ask "why" of is the record explaining itself.
 */
function Labelled({
  label,
  note,
  why,
  children,
}: {
  readonly label: string;
  readonly note: string;
  /** Why the note reads the way it does, in one line, or nothing to explain. */
  readonly why?: string | undefined;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-2xs text-muted">{label}</span>
        <span className="text-2xs text-muted/70 italic">{note}</span>
        {why === undefined ? null : <Hint text={why} />}
      </div>
      {children}
    </div>
  );
}

/**
 * The message the record would have refused with, under the field that caused
 * it, while the operator can still fix it in place.
 */
function Inline({ message }: { readonly message: string | null }): ReactElement | null {
  return message === null ? null : (
    <p role="alert" className="mt-1.5 mb-0 text-xs text-danger">
      {message}
    </p>
  );
}

/** The project keys this company already records, so a name cannot collide. */
function recordedKeys(document: CompanyBundleDocument): readonly string[] {
  return document.resources
    .filter((resource) => resource.component.kind === "project")
    .map((resource) => resource.component.key);
}

/** The recorded bundle with one authored project in it, and nothing else moved. */
function withProject(
  authoring: Authoring,
  draft: Draft,
  goals: readonly string[]
): CompanyBundleDocument {
  const payload = payloadOf(draft, goals);
  const resource = resourceOf(
    { kind: "project", schemaRef: PROJECT_SCHEMA_REF, payload, source: AUTHORED_HERE },
    authoring.tenant
  );
  return {
    ...authoring.recorded,
    resources: [...authoring.recorded.resources, resource],
  };
}

/**
 * What a project authored on this screen records about where it came from. An
 * authored pack names the file it was read out of; these were typed here, and
 * the provenance says so rather than borrowing a path or another screen.
 */
export const AUTHORED_HERE = "ctower-web/projects";
