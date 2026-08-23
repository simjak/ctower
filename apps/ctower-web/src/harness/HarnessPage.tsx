import { useCallback, useRef, useState } from "react";
import type { ReactElement } from "react";
import type {
  CompanyBundleCommandResult,
  CompanyBundleDocument,
  ComponentKind,
} from "@ctower/client";
import type { Answer } from "../api/client";
import { cn } from "../ui/cn";
import { Field } from "../ui/form";
import { Mono, PageHead } from "../ui/primitives";
import { ReviewPanel } from "../wizard/review/ReviewPanel";
import { standingOf } from "../wizard/standing";
import type { Standing } from "../wizard/standing";
import { useApply } from "../wizard/useApply";
import { AgentsPanel } from "./AgentsPanel";
import { CrewPanel } from "./CrewPanel";
import { FilesPanel } from "./FilesPanel";
import { ProjectsPanel } from "./ProjectsPanel";
import { WorkspacesPanel } from "./WorkspacesPanel";

/**
 * The harness screen: where an operator sets the work up.
 *
 * Everything an operator declares here — a project, an agent, and the surfaces
 * that land beside them — is one act at the record: the company bundle is
 * authored, checked, planned, and applied. There is no `createProject` and no
 * `createAgent` operation to reach for; the four bundle operations are the
 * capability, and the first-run wizard already proved this exact path. So this
 * page owns the ceremony once and every tab hands it a document.
 *
 * The tabs are a plain array, declared where the panels' own props are already
 * in scope, so a surface that lands later is one line and nothing else. Three
 * lanes built into this array and it is the only registry: one title, one
 * subtitle, one tab list. A tab that keeps its own read or its own ceremony
 * does so inside its panel and never grows a second head on this page.
 */
export function HarnessPage({
  recorded,
  project,
  onApplied,
}: {
  /** The active bundle, exactly as `exportCompanyBundle` returned it. */
  readonly recorded: CompanyBundleDocument;
  /** The project key the rail's switcher is pointed at, if this company has one. */
  readonly project: string | null;
  /** An accepted apply changed what is recorded; the app re-reads it. */
  readonly onApplied: () => void;
}): ReactElement {
  const ceremony = useCeremony(recorded, onApplied);
  const [here, setHere] = useState("projects");

  if (ceremony.review !== null) {
    return (
      <ReviewPanel
        review={ceremony.review}
        applied={ceremony.applied}
        armed={ceremony.armed}
        onArm={ceremony.setArmed}
        onApply={ceremony.apply}
        onRetry={ceremony.retry}
        onBack={ceremony.close}
        backLabel="Back to setup"
      />
    );
  }

  const tabs: readonly Tab[] = [
    {
      key: "projects",
      label: "Projects",
      element: <ProjectsPanel authoring={ceremony.authoring} current={project} />,
    },
    { key: "agents", label: "Agents", element: <AgentsPanel authoring={ceremony.authoring} /> },
    {
      key: "crew",
      label: "Crew",
      element: <CrewPanel recorded={recorded} onRecorded={onApplied} />,
    },
    { key: "files", label: "Agent files", element: <FilesPanel /> },
    { key: "workspaces", label: "Workspaces", element: <WorkspacesPanel /> },
    // One line per surface, and nothing else in this array.
  ];
  const current = tabs.find((tab) => tab.key === here) ?? tabs[0];

  return (
    <>
      <PageHead title="Harnesses" subtitle={<span>{PURPOSE}</span>} />
      <TabBar tabs={tabs} here={current?.key ?? ""} onGo={setHere} />
      {current?.element}
    </>
  );
}

/**
 * The one line that says what this screen is for. One line, and no second one.
 *
 * It names what an operator can actually do here and stops. Workspaces are on
 * this screen to say they are not built yet, so putting them in the sentence
 * that promises the work would be the pretending `DESIGN.md` forbids.
 */
const PURPOSE = "Set up the work: the projects, agents, crews and files this company runs.";

/**
 * What a component authored on this screen records about where it came from.
 * An authored pack names the file it was read out of; these were typed here,
 * and the provenance says so rather than borrowing a path or another screen.
 */
export const AUTHORED_HERE = "ctower-web/harness";

export interface Tab {
  readonly key: string;
  readonly label: string;
  readonly element: ReactElement;
}

/**
 * What a tab is handed: what is recorded, whose tenant it is, and the one way
 * to change it. A panel composes the next document out of the recorded one and
 * hands it over; from there every tab meets the same check, the same plan, and
 * the same operator-authority apply.
 */
export interface Authoring {
  readonly recorded: CompanyBundleDocument;
  /** The company key every component this screen mints is scoped to. */
  readonly tenant: string;
  readonly propose: (next: CompanyBundleDocument) => void;
}

interface Ceremony {
  readonly authoring: Authoring;
  /** Null until something is proposed; there is no review of nothing. */
  readonly review: Answer<Standing> | null;
  readonly applied: Answer<CompanyBundleCommandResult> | null;
  readonly armed: boolean;
  readonly setArmed: (armed: boolean) => void;
  readonly apply: (standing: Standing) => void;
  /** Present only when the same command may honestly be sent again. */
  readonly retry: (() => void) | null;
  readonly close: () => void;
}

const ASKING = { kind: "asking" } as const;

/**
 * Check, plan, apply — held once for every tab on this screen.
 *
 * The check-plan and the command itself are the shared ones: there is one
 * company bundle and one ceremony over it, so this screen reaches for
 * `standingOf` and `useApply` rather than keeping a second copy of the only
 * write this browser can send.
 *
 * What is this screen's own is the sequencing. The operator can leave the
 * review or propose something else while a plan is out, so each asynchronous
 * act carries the generation it started in and a response from a superseded
 * generation is dropped rather than arming an apply for a document nobody is
 * looking at.
 */
function useCeremony(recorded: CompanyBundleDocument, onApplied: () => void): Ceremony {
  const [review, setReview] = useState<Answer<Standing> | null>(null);
  const [armed, setArmed] = useState(false);
  const generation = useRef(0);
  const { applied, apply, retry, forget } = useApply(generation, onApplied);

  const supersede = useCallback((): number => {
    generation.current += 1;
    return generation.current;
  }, []);

  const propose = useCallback(
    (next: CompanyBundleDocument): void => {
      const mine = supersede();
      setReview(ASKING);
      setArmed(false);
      forget();
      void (async (): Promise<void> => {
        const answer = await standingOf(next);
        if (generation.current === mine) {
          setReview(answer);
        }
      })();
    },
    [forget, supersede]
  );

  const close = useCallback((): void => {
    supersede();
    setReview(null);
    setArmed(false);
    forget();
  }, [forget, supersede]);

  return {
    authoring: { recorded, tenant: recorded.company.key, propose },
    review,
    applied,
    armed,
    setArmed,
    apply,
    retry,
    close,
  };
}

/**
 * What every panel on this screen shares: choosing a component that is already
 * recorded.
 *
 * A project names a goal, an agent names a harness, and both of them mean one
 * exact revision of something the bundle already carries. So the choice is over
 * the record and never over free text, and a company that carries none of a
 * kind says so instead of offering an empty control.
 */
export interface Choice {
  /** `key@revision` — the reference form every payload uses. */
  readonly value: string;
  /** The name a person recognises, when the payload carries one. */
  readonly label: string | null;
}

export function choicesOf(document: CompanyBundleDocument, kind: ComponentKind): readonly Choice[] {
  return document.resources
    .filter((resource) => resource.component.kind === kind)
    .map((resource) => {
      const component = resource.component;
      const name = resource.payload.display_name;
      return {
        value: `${component.key}@${String(component.revision)}`,
        // A component whose payload names nothing is shown by its reference
        // alone. Repeating the key as though it were a display name puts the
        // same string on the control twice and calls one of them a name.
        label: typeof name === "string" && name.length > 0 ? name : null,
      };
    });
}

export function Picker({
  label,
  hint,
  choices,
  value,
  onValue,
  empty,
}: {
  readonly label: string;
  readonly hint: string;
  readonly choices: readonly Choice[];
  readonly value: string;
  readonly onValue: (value: string) => void;
  /** One sentence, for a company that carries none of this kind yet. */
  readonly empty: string;
}): ReactElement {
  if (choices.length === 0) {
    return (
      <Field label={label}>
        <p className="m-0 text-sm text-muted">{empty}</p>
      </Field>
    );
  }
  return (
    <Field label={label} hint={hint}>
      <div className="flex flex-wrap gap-2">
        {choices.map((choice) => (
          <button
            key={choice.value}
            type="button"
            aria-pressed={choice.value === value}
            onClick={(): void => {
              onValue(choice.value);
            }}
            className={cn(
              "cursor-pointer rounded-sm border px-3 py-1.5 text-left text-sm",
              choice.value === value
                ? "border-amber bg-amber/10 text-fg"
                : "border-line bg-bg text-muted hover:bg-raised hover:text-fg"
            )}
          >
            {choice.label === null ? null : <span className="mr-1.5">{choice.label}</span>}
            <Mono className="text-muted">{choice.value}</Mono>
          </button>
        ))}
      </div>
    </Field>
  );
}

/**
 * The tabs. Buttons in a tablist, so the keyboard reaches every one of them and
 * the amber edge marks where the operator is — the rail's own vocabulary, one
 * level in.
 */
function TabBar({
  tabs,
  here,
  onGo,
}: {
  readonly tabs: readonly Tab[];
  readonly here: string;
  readonly onGo: (key: string) => void;
}): ReactElement {
  return (
    <div role="tablist" aria-label="Setup" className="mb-4 flex gap-1 border-b border-line">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={tab.key === here}
          onClick={(): void => {
            onGo(tab.key);
          }}
          className={cn(
            "-mb-px cursor-pointer border-b-2 px-3 py-2 text-sm",
            tab.key === here
              ? "border-amber font-semibold text-fg"
              : "border-transparent text-muted hover:bg-raised hover:text-fg"
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
