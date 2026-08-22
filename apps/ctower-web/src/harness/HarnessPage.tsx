import { useCallback, useRef, useState } from "react";
import type { ReactElement } from "react";
import type {
  CompanyBundleCommandResult,
  CompanyBundleDocument,
  ComponentKind,
} from "@ctower/client";
import { ask, commands, computations } from "../api/client";
import type { Answer } from "../api/client";
import { cn } from "../ui/cn";
import { Field } from "../ui/form";
import { Mono, PageHead } from "../ui/primitives";
import { commandKeyFor } from "../wizard/apply/commandKey";
import { ReviewPanel } from "../wizard/review/ReviewPanel";
import type { Standing } from "../wizard/useCompany";
import { AgentsPanel } from "./AgentsPanel";
import { ProjectsPanel } from "./ProjectsPanel";

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
 * in scope, so a surface that lands later is one line and nothing else.
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

/** The one line that says what this screen is for. One line, and no second one. */
const PURPOSE = "Set up the work: the projects and the agents this company runs.";

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
 * Each asynchronous act carries the generation it started in, because the
 * operator can leave the review or propose something else while a plan is out.
 * A response from a superseded generation is dropped rather than arming an
 * apply for a document nobody is looking at.
 */
function useCeremony(recorded: CompanyBundleDocument, onApplied: () => void): Ceremony {
  const [review, setReview] = useState<Answer<Standing> | null>(null);
  const [applied, setApplied] = useState<Answer<CompanyBundleCommandResult> | null>(null);
  const [armed, setArmed] = useState(false);
  const [sent, setSent] = useState<Standing | null>(null);
  const generation = useRef(0);

  const supersede = useCallback((): number => {
    generation.current += 1;
    return generation.current;
  }, []);

  const propose = useCallback(
    (next: CompanyBundleDocument): void => {
      const mine = supersede();
      setReview(ASKING);
      setApplied(null);
      setArmed(false);
      setSent(null);
      void (async (): Promise<void> => {
        const answer = await standingOf(next);
        if (generation.current === mine) {
          setReview(answer);
        }
      })();
    },
    [supersede]
  );

  const send = useCallback(
    (standing: Standing): void => {
      const mine = generation.current;
      setApplied(ASKING);
      void (async (): Promise<void> => {
        const answer = await ask(() =>
          commands.applyCompanyBundle({
            IdempotencyKey: commandKeyFor(standing.plan.plan_digest),
            body: {
              bundle: standing.document,
              expected_active_version: standing.plan.base_version,
              plan_digest: standing.plan.plan_digest,
            },
          })
        );
        if (generation.current !== mine) {
          return;
        }
        setApplied(answer);
        // Only acceptance changed what is recorded. `durability_pending` did
        // not, so nothing is re-read on it and the retry stays offered.
        if (answer.kind === "answered" && answer.value.durability_state === "accepted") {
          onApplied();
        }
      })();
    },
    [onApplied]
  );

  const close = useCallback((): void => {
    supersede();
    setReview(null);
    setApplied(null);
    setArmed(false);
    setSent(null);
  }, [supersede]);

  return {
    authoring: { recorded, tenant: recorded.company.key, propose },
    review,
    applied,
    armed,
    setArmed,
    apply: (standing: Standing): void => {
      setSent(standing);
      send(standing);
    },
    retry:
      sent === null || applied === null || !resendable(applied)
        ? null
        : (): void => {
            send(sent);
          },
    close,
  };
}

/**
 * Whether sending the same command again is the honest next move. A refusal is
 * not: ctower read the command and said no. The other three are — it was not
 * reached, its answer could not be read, or it has not confirmed durability —
 * and the shared idempotency key is what makes finding out safe.
 */
function resendable(applied: Answer<CompanyBundleCommandResult>): boolean {
  switch (applied.kind) {
    case "asking":
    case "refused":
      return false;
    case "unreachable":
    case "malformed":
      return true;
    case "answered":
      return applied.value.durability_state !== "accepted";
  }
}

/** Check and plan one document, stopping at the first thing that is not an answer. */
async function standingOf(bundle: CompanyBundleDocument): Promise<Answer<Standing>> {
  const validation = await ask(() => computations.validateCompanyBundle({ body: { bundle } }));
  if (validation.kind !== "answered") {
    return validation;
  }
  const plan = await ask(() => computations.planCompanyBundle({ body: { bundle } }));
  if (plan.kind !== "answered") {
    return plan;
  }
  return {
    kind: "answered",
    value: { document: bundle, validation: validation.value, plan: plan.value },
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
