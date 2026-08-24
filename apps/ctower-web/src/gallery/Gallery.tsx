import { useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { AgentRow } from "../agents/AgentRow";
import type { Agent } from "../agents/AgentRow";
import { HarnessPicker } from "../agents/HarnessPicker";
import { harnessChoices } from "../agents/harnesses";
import type { HarnessFamily } from "../agents/harnesses";
import { agentIn } from "../agents/instructions/agent";
import { FileEditor } from "../agents/instructions/FileEditor";
import { FileList } from "../agents/instructions/FileList";
import { draftOf } from "../agents/instructions/compose";
import type { FileDraft } from "../agents/instructions/compose";
import { resourceById } from "../agents/instructions/read";
import { Card, PageHead } from "../ui/primitives";
import { TooltipScope } from "../ui/form";
import { ThemeToggle } from "../app/ThemeToggle";
import { ADA, COMPANY, STAFF } from "./stories";

/**
 * The bench: two components, alone, in every state they have.
 *
 * It is not a screen and it is not a destination. Nothing in `destinations.ts`
 * points here, `vite build` never sees this page — `index.html` is the app's one
 * entry — and no read runs, so the bench answers to no tower and can be looked
 * at on any host. It exists so a component can be reviewed and screenshotted as
 * itself, in both themes, before any page decides where it goes.
 */
export function Gallery(): ReactElement {
  return (
    // The app installs this scope once at its root; the bench is a second root
    // and needs its own, or every field hint on it throws instead of opening.
    <TooltipScope>
      <main className="mx-auto max-w-[1000px] px-6 py-8">
        <PageHead title="Agent components" subtitle="Components on their own. Nothing is wired.">
          <ThemeToggle />
        </PageHead>
        <div className="space-y-8">
          <PickerStories />
          <RowStories />
          <InstructionStories />
        </div>
      </main>
    </TooltipScope>
  );
}

/** The card picker, before a choice and after one. */
function PickerStories(): ReactElement {
  const [chosen, setChosen] = useState<HarnessFamily | null>(null);
  return (
    <>
      <Story title="Harness picker — nothing chosen" note={chose(chosen)}>
        <HarnessPicker choices={harnessChoices()} value={chosen} onChoose={setChosen} />
      </Story>
      <Story title="Harness picker — a choice already made" note="Arrow keys move between cards.">
        <HarnessPicker choices={harnessChoices()} value="codex" onChoose={(): void => undefined} />
      </Story>
    </>
  );
}

/** Every state a row has, including the two that are absences. */
function RowStories(): ReactElement {
  const [opened, setOpened] = useState<string | null>(null);
  return (
    <Story
      title="Agent rows — active, idle, paused, error, and nothing recorded"
      note={opened === null ? "Open a row." : `Opened ${opened}.`}
    >
      <Card>
        {STAFF.map((agent) => (
          <AgentRow
            key={agent.name}
            agent={agent}
            onOpen={(who: Agent): void => {
              setOpened(who.name);
            }}
          />
        ))}
      </Card>
    </Story>
  );
}

/**
 * What one agent is told, driven by a fixture company.
 *
 * The Instructions tab reads the company for itself, so the tab as a whole
 * needs a tower and is not on the bench. Its two halves do not: the sidebar
 * takes the agent's own resolved files, and the editor takes one draft. So what
 * is drawn here is the resolution — `agentIn` walking `persona_ref`,
 * `skill_refs` and `tool_refs` — and everything the operator meets once a file
 * is open, including the `Advanced` disclosure that holds the record's own
 * words.
 */
function InstructionStories(): ReactElement {
  const agent = agentIn(COMPANY, ADA);
  const [openId, setOpenId] = useState<string | null>(agent?.files[0]?.id ?? null);
  const draft = draftFor(openId);

  if (agent === null) {
    return <Story title="Instructions" note="The fixture names no agent." children={null} />;
  }
  return (
    <Story
      title="Instructions — one agent's own files, and the file that is open"
      note="Open Advanced for the record's own words."
    >
      <div className="grid gap-4 md:grid-cols-[260px_minmax(0,1fr)]">
        <FileList files={agent.files} openId={openId} onOpen={setOpenId} />
        {draft === null ? null : (
          <FileEditor
            document={COMPANY}
            draft={draft}
            onDraft={(): void => undefined}
            edited={false}
            onReview={(): void => undefined}
          />
        )}
      </div>
    </Story>
  );
}

function draftFor(openId: string | null): FileDraft | null {
  if (openId === null) {
    return null;
  }
  const resource = resourceById(COMPANY, openId);
  return resource === null ? null : draftOf(resource);
}

function chose(chosen: HarnessFamily | null): string {
  return chosen === null ? "Nothing chosen yet." : "A card is chosen.";
}

function Story({
  title,
  note,
  children,
}: {
  readonly title: string;
  readonly note: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <section>
      <header className="mb-2 flex items-baseline gap-3 border-b border-line pb-1.5">
        <h2 className="m-0 flex-1 text-sm font-semibold">{title}</h2>
        <span className="text-2xs text-muted">{note}</span>
      </header>
      {children}
    </section>
  );
}
