import { useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { AgentRow } from "../agents/AgentRow";
import { AgentsRail } from "../agents/AgentsRail";
import type { Agent } from "../agents/AgentRow";
import { HarnessPicker } from "../agents/HarnessPicker";
import { harnessChoices } from "../agents/harnesses";
import type { HarnessFamily } from "../agents/harnesses";
import { Card, PageHead } from "../ui/primitives";
import { ThemeToggle } from "../app/ThemeToggle";
import { PAYROLL, STAFF } from "./stories";

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
    <main className="mx-auto max-w-[1000px] px-6 py-8">
      <PageHead title="Agent components" subtitle="Two components, on their own. Nothing is wired.">
        <ThemeToggle />
      </PageHead>
      <div className="space-y-8">
        <PickerStories />
        <RowStories />
        <RailStories />
      </div>
    </main>
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
