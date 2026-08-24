import { useMemo, useState } from "react";
import { Bot, ChevronLeft } from "lucide-react";
import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { Button, Chip } from "../ui/primitives";
import { Inert } from "../projects/Inert";
import { sessionsOfProject, useSessions } from "../cockpit/useSessions";
import type { Answer } from "../api/client";
import type { TicketSession } from "@ctower/client";
import { Dashboard } from "./Dashboard";
import { Held } from "./Held";
import { standingOf } from "./status";
import { UNBUILT } from "./tabs";
import type { TabKey } from "./tabs";
import type { AgentFacts } from "./read";

/**
 * One agent's own screen.
 *
 * The header is what a person would say about a colleague: who this is, what it
 * runs on, and what it is doing. The last of those is the one thing the record
 * cannot answer — no read reports an agent's state — so the pill draws the
 * unknown standing the shared vocabulary already has, no mark and the word, and
 * the three actions beside it are drawn as the acts they would be rather than
 * as buttons that would do nothing.
 *
 * Nine tabs, and only three of them have a read behind them. That ratio is the
 * screen's whole point: the reference console's agent home is the shape the
 * operator asked for, and drawing six of its tabs with invented content would
 * make the three real ones worthless. Each unbuilt tab says what it will hold
 * and why it cannot hold it yet.
 *
 * A tab is a place inside a screen, not a screen of its own, so it does not
 * enter the address — the address says which agent, and that is what survives a
 * reload. The same rule the project workspace settled.
 */
export function AgentHome({
  agent,
  onBack,
}: {
  readonly agent: AgentFacts;
  /** Where the trail goes back to. */
  readonly onBack: () => void;
}): ReactElement {
  const [here, setHere] = useState<TabKey>("dashboard");
  const standing = standingOf(null);
  // The projects this agent holds a seat in, which is the one honest reach from
  // an agent to work the record can serve. An agent seated nowhere asks for
  // nothing rather than asking for every project the company has.
  const sessions = useSessions(useMemo(() => [...agent.projects], [agent.projects]));

  return (
    <>
      <nav aria-label="Trail" className="mb-3 flex items-center gap-1.5 text-2xs text-muted">
        <Button variant="quiet" size="sm" className="-ml-2.5" onClick={onBack}>
          <ChevronLeft /> Agents
        </Button>
        <span aria-hidden>›</span>
        <span className="truncate text-fg">{agent.name}</span>
      </nav>

      <header className="mb-4 flex flex-wrap items-center gap-3">
        <span className="grid size-9 shrink-0 place-content-center rounded-md border border-line bg-raised">
          <Bot aria-hidden className="size-5 text-muted" />
        </span>
        <span className="min-w-0 flex-1">
          <h1 className="m-0 truncate text-xl leading-tight font-bold tracking-[-0.02em]">
            {agent.name}
          </h1>
          {/* What it runs on, when this console can name it. A harness whose
              adapter nothing here declares gets no line at all rather than a
              sentence about the absence — the Configuration tab is where that
              gap is stated, with its reason on the disclosure. */}
          {agent.harness === null ? null : (
            <span className="mt-0.5 block truncate text-xs text-muted">
              Runs on {agent.harness}
            </span>
          )}
        </span>
        <Chip tone={standing.tone}>{standing.word}</Chip>
        <Inert
          className="chip"
          reason="Giving an agent a task is the runner's, and no browser reaches it."
        >
          Assign task
        </Inert>
        <Inert className="chip" reason="Nothing schedules or starts a heartbeat for an agent yet.">
          Run heartbeat
        </Inert>
        <Inert
          className="chip"
          reason="A recorded agent holds no state, so there is none to pause."
        >
          Pause
        </Inert>
      </header>

      <div
        role="tablist"
        aria-label="Agent"
        className="mb-4 flex flex-wrap gap-1 border-b border-line"
      >
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={tab.key === here}
            onClick={(): void => {
              setHere(tab.key);
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

      <Panel here={here} agent={agent} work={workOf(agent, sessions)} />
    </>
  );
}

const TABS: readonly { readonly key: TabKey; readonly label: string }[] = [
  { key: "dashboard", label: "Dashboard" },
  { key: "instructions", label: "Instructions" },
  { key: "skills", label: "Skills" },
  { key: "configuration", label: "Configuration" },
  { key: "secrets", label: "Secrets" },
  { key: "tools", label: "Tools" },
  { key: "runs", label: "Runs" },
  { key: "audit", label: "Audit" },
  { key: "budget", label: "Budget" },
];

function Panel({
  here,
  agent,
  work,
}: {
  readonly here: TabKey;
  readonly agent: AgentFacts;
  readonly work: Answer<readonly TicketSession[]>;
}): ReactElement {
  switch (here) {
    case "dashboard":
      return <Dashboard work={work} />;
    case "skills":
      return <Held what="skills" held={agent.skills} reason={UNBUILT.skills} />;
    case "tools":
      return <Held what="tools" held={agent.tools} reason={UNBUILT.tools} />;
    case "configuration":
      return <Configuration agent={agent} />;
    case "instructions":
    case "secrets":
    case "runs":
    case "audit":
    case "budget":
      return <Unbuilt reason={UNBUILT[here]} />;
  }
}

/** What this agent is set to, which is the two things a record keeps of it. */
function Configuration({ agent }: { readonly agent: AgentFacts }): ReactElement {
  return (
    <dl className="m-0 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <Setting label="Harness" value={agent.harness} reason={UNBUILT.harnessName} />
      <Setting
        label="Seats"
        value={agent.seats === 0 ? null : String(agent.seats)}
        reason="This agent is assigned to no seat, so nothing has been given to it to do."
      />
      <Setting
        label="Skills"
        value={agent.skills.length === 0 ? null : agent.skills.join(", ")}
        reason={UNBUILT.skills}
      />
    </dl>
  );
}

function Setting({
  label,
  value,
  reason,
}: {
  readonly label: string;
  readonly value: string | null;
  readonly reason: string;
}): ReactElement {
  return (
    <div className="min-w-0">
      <dt className="text-2xs text-muted">{label}</dt>
      <dd className="m-0 mt-1 text-sm">
        {value ?? (
          <Inert className="text-sm" reason={reason}>
            none recorded
          </Inert>
        )}
      </dd>
    </div>
  );
}

/** A tab whose read does not exist, drawn as `DESIGN.md` draws a destination. */
function Unbuilt({ reason }: { readonly reason: string }): ReactElement {
  return (
    <div className="grid place-content-center rounded-md border border-line bg-card p-10 text-center">
      <p className="m-0 text-sm font-medium text-muted">Not built yet</p>
      <p className="mt-1 mb-0 max-w-[46ch] text-xs text-balance text-muted">{reason}</p>
    </div>
  );
}

/**
 * The work this agent's projects have recorded, gathered into one answer.
 *
 * An agent seated in two projects has two independent reads, and one that has
 * not answered must not take the other down with it — so anything still asking
 * keeps the whole tab asking, and a project that refused is the answer the tab
 * shows rather than a partial total presented as a total.
 */
function workOf(
  agent: AgentFacts,
  sessions: ReadonlyMap<string, Answer<readonly TicketSession[]>>
): Answer<readonly TicketSession[]> {
  if (agent.projects.length === 0) {
    return { kind: "answered", value: [] };
  }
  const answers = agent.projects.map((project) => sessionsOfProject(sessions.get(project)));
  const unanswered = answers.find((answer) => answer.kind !== "answered");
  if (unanswered !== undefined) {
    return unanswered;
  }
  return {
    kind: "answered",
    value: answers.flatMap((answer) => (answer.kind === "answered" ? answer.value : [])),
  };
}
