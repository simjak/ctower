import { useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { AgentRow } from "../agents/AgentRow";
import { AgentsRail } from "../agents/AgentsRail";
import type { AgentFacts } from "../agents/read";
import { HarnessPicker } from "../agents/HarnessPicker";
import { harnessChoices } from "../agents/harnesses";
import type { HarnessFamily } from "../agents/harnesses";
import { agentIn } from "../agents/instructions/agent";
import { FileEditor } from "../agents/instructions/FileEditor";
import { FileList } from "../agents/instructions/FileList";
import { draftOf } from "../agents/instructions/compose";
import type { FileDraft } from "../agents/instructions/compose";
import { resourceById } from "../agents/instructions/read";
import { Configuration } from "../projects/home/Configuration";
import { Card, PageHead } from "../ui/primitives";
import { TooltipScope } from "../ui/form";
import { ThemeToggle } from "../app/ThemeToggle";
import { ADA, BARE, COMPANY, CONTROL_PLANE, PAYROLL, STAFF } from "./stories";
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
        <PageHead title="Components" subtitle="Components on their own. Nothing is wired.">
          <ThemeToggle />
        </PageHead>
        <div className="space-y-8">
          <PickerStories />
          <RowStories />
          <RailStories />
          <InstructionStories />
          <ConfigurationStories />
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
            onOpen={(who: AgentFacts): void => {
              setOpened(who.name);
            }}
          />
        ))}
      </Card>
    </Story>
  );
}

/**
 * The rail section, at the two sizes that matter: a company with more staff
 * than the rail carries, and one with none at all.
 */
function RailStories(): ReactElement {
  const [opened, setOpened] = useState<string | null>(null);
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <Story
        title="Rail — eight agents, six drawn"
        note={opened === null ? "Open one." : `Opened ${opened}.`}
      >
        <div className="w-[200px] border border-line bg-card py-2">
          <AgentsRail
            agents={PAYROLL}
            here
            current={opened}
            onOpen={setOpened}
            onSeeAll={(): void => {
              setOpened(null);
            }}
          />
        </div>
      </Story>
      <Story title="Rail — a company with no agent yet" note="One line, and the way to make one.">
        <div className="w-[200px] border border-line bg-card py-2">
          <AgentsRail
            agents={[]}
            here={false}
            current={null}
            onOpen={(): void => undefined}
            onSeeAll={(): void => undefined}
          />
        </div>
      </Story>
    </div>
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

/**
 * A project's Configuration tab, at the two sizes the record produces.
 *
 * The tab is a pure read over one project's recorded facts, so the whole of it
 * fits on the bench and can be judged in both themes without a tower. What the
 * two stories prove together is the rule the screen is built on: a row renders
 * where the bundle answers and is absent where it does not — the second draws
 * one card, one row, and no Codebase card at all, rather than a column of
 * `Not set`.
 */
function ConfigurationStories(): ReactElement {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Story
        title="Configuration — everything the record holds"
        note="Four facts, two cards, one line."
      >
        <Configuration project={CONTROL_PLANE} />
      </Story>
      <Story
        title="Configuration — a project the record says less about"
        note="Unanswered rows are absent, not empty."
      >
        <Configuration project={BARE} />
      </Story>
    </div>
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
