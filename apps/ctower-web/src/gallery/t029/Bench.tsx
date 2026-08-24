import { useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { PageHead } from "../../ui/primitives";
import { ThemeToggle } from "../../app/ThemeToggle";
import { CrewsScreen } from "./CrewsScreen";
import { NewCrew } from "./NewCrew";
import { ATTRIBUTED, NOBODY, TODAY, UNSTAFFED } from "./stories";

/**
 * T-029's bench: the Crews screen, alone, in every state it has.
 *
 * It is not a screen and it is not a destination. Nothing in `destinations.ts`
 * points here, `vite build` never sees this page, and no read runs — so this
 * bench answers to no tower and can be looked at on any host. Nothing is wired.
 *
 * The two pictures of the same list are the point of the review. The first is
 * what a live tower can honestly draw today; the second is the same layout once
 * a recorded run can name the crew it ran as. Both are here at once because the
 * difference between them is the ruling being asked for.
 */
export function CrewsBench(): ReactElement {
  const [opened, setOpened] = useState<string | null>(null);
  const [made, setMade] = useState(false);
  return (
    <main className="mx-auto max-w-[1000px] px-6 py-8">
      <PageHead title="Crews" subtitle="One screen, in every state it has. Nothing is wired.">
        <ThemeToggle />
      </PageHead>
      <div className="space-y-10">
        <Story
          title="What the record answers today"
          note="Names and harnesses are real. No row claims a state."
        >
          <CrewsScreen
            projects={TODAY}
            onNew={(): void => {
              setMade(true);
            }}
            onOpen={(crew): void => {
              setOpened(crew.name);
            }}
          />
        </Story>
        <Story
          title="The same rows once a run names its crew"
          note={opened === null ? "Open a row." : `Opened ${opened}.`}
        >
          <CrewsScreen
            projects={ATTRIBUTED}
            onNew={(): void => {
              setMade(true);
            }}
            onOpen={(crew): void => {
              setOpened(crew.name);
            }}
          />
        </Story>
        <Story
          title="New crew"
          note={made ? "Opened from the button above." : "What the button opens."}
        >
          <NewCrew />
        </Story>
        <Story title="A company with no crew yet" note="One sentence, and the one way to act.">
          <CrewsScreen projects={NOBODY} onNew={noop} onOpen={noop} />
        </Story>
        <Story
          title="A project with nobody on it"
          note="Drawn beside a staffed one, so the absence reads as an absence."
        >
          <CrewsScreen projects={UNSTAFFED} onNew={noop} onOpen={noop} />
        </Story>
      </div>
    </main>
  );
}

function noop(): void {
  return undefined;
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
      <header className="mb-3 flex items-baseline gap-3 border-b border-line pb-1.5">
        <h2 className="m-0 flex-1 text-sm font-semibold">{title}</h2>
        <span className="text-2xs text-muted">{note}</span>
      </header>
      {children}
    </section>
  );
}
