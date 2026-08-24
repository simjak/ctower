import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument, ComponentKind } from "@ctower/client";
import { cn } from "../ui/cn";
import { Field } from "../ui/form";
import { PageHead } from "../ui/primitives";
import { useCeremony } from "../wizard/ceremony";
import { ReviewPanel } from "../wizard/review/ReviewPanel";
import { AgentsPanel } from "./AgentsPanel";
import { CrewPanel } from "./CrewPanel";
import { WorkspacesPanel } from "./WorkspacesPanel";

/**
 * The harness screen: the runtime the staff run on.
 *
 * Agents, crews and the workspaces they run in — everything about *how* the
 * work is done, and nothing about *what* is being built. A project is not a
 * harness, so it is not here: it is a thing the company has, and the Projects
 * screen in the company workspace owns both listing one and making one.
 *
 * What an agent is *told* is not here either, for the same reason and not for a
 * new one. A persona, a skill and a tool belong to the agent that names them,
 * not to the runtime it happens to run on, and the harness had no way to say
 * which of them any one agent read — so the list has moved under the agent, to
 * `agents/instructions`, and this screen does not keep a copy.
 *
 * Everything an operator declares here is one act at the record: the company
 * bundle is authored, checked, planned, and applied. There is no `createAgent`
 * operation to reach for; the four bundle operations are the capability, and
 * the first-run wizard already proved this exact path. So this page owns the
 * ceremony once and every tab hands it a document.
 *
 * The tabs are a plain array, declared where the panels' own props are already
 * in scope, so a surface that lands later is one line and nothing else. It is
 * the only registry: one title, one subtitle, one tab list. A tab that keeps
 * its own read or its own ceremony does so inside its panel and never grows a
 * second head on this page.
 */
export function HarnessPage({
  recorded,
  onApplied,
}: {
  /** The active bundle, exactly as `exportCompanyBundle` returned it. */
  readonly recorded: CompanyBundleDocument;
  /** An accepted apply changed what is recorded; the app re-reads it. */
  readonly onApplied: () => void;
}): ReactElement {
  const ceremony = useCeremony(recorded, onApplied);
  const [here, setHere] = useState("agents");

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
    { key: "agents", label: "Agents", element: <AgentsPanel authoring={ceremony.authoring} /> },
    {
      key: "crew",
      label: "Crew",
      element: <CrewPanel recorded={recorded} onRecorded={onApplied} />,
    },
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
const PURPOSE = "Set up the runtime: the agents and crews this company runs work on.";

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
 * What every panel on this screen shares: choosing a component that is already
 * recorded.
 *
 * An agent names a harness, and that means one exact revision of something the
 * bundle already carries. So the choice is over the record and never over free
 * text, and a company that carries none of a kind says so instead of offering
 * an empty control.
 *
 * The reference the payload will carry is the value; it is machine text and it
 * never renders. What renders is the name a person gave the thing — and a
 * component whose payload named nothing renders as the one honest thing left
 * to say about it rather than as its key.
 */
export interface Choice {
  /** The reference form every payload uses. It travels; it does not render. */
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
            {choice.label ?? "Unnamed"}
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
