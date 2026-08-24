import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { Button, Card, PageHead } from "../ui/primitives";
import { Hint } from "../ui/form";
import { cn } from "../ui/cn";
import { AgentRow } from "./AgentRow";
import { agentsIn } from "./read";
import type { ListedAgent } from "./read";
import type { AgentStatus } from "./status";

/**
 * Agents: everyone this company has, one row each.
 *
 * The row is the whole screen. There is no table of properties, because an
 * agent is a member of staff here and not a component: a name, the job, what it
 * runs on, when it last ran, how it is doing. Nothing on this page is a key, a
 * revision or a digest, and the address is the only place a key travels.
 *
 * **The two lines this screen has to be honest about.** The record keeps a
 * persona's name and the harness a profile pairs it with, and nothing else a
 * person would call staffing: `ctower.persona/v1` has no title, no
 * `agent-profile` field carries a model, and no read ties a recorded run to an
 * agent. All three schemas are closed, so this is a gap in the record and not a
 * field this screen forgot to fetch. The gap is said once, in one line, and the
 * columns it owns stay empty — a row that filled them from a near-enough field
 * would be the console making up staff.
 */
export function AgentsPage({
  document,
  current,
  onOpen,
  onNew,
}: {
  readonly document: CompanyBundleDocument;
  /** The agent the rail is pointing at, when it is pointing at one. */
  readonly current: string | null;
  readonly onOpen: (key: string) => void;
  /** Where an agent is made today. */
  readonly onNew: () => void;
}): ReactElement {
  const agents = agentsIn(document);
  const [filter, setFilter] = useState<Filter>("all");
  const shown = agents.filter((listed) => matches(listed, filter));

  return (
    <>
      <PageHead title="Agents" subtitle={<Counted agents={agents} />}>
        <Button variant="primary" onClick={onNew}>
          New agent
        </Button>
      </PageHead>

      {agents.length === 0 ? (
        <Card className="p-6 text-sm text-muted">
          No agent is in this company yet.{" "}
          <button type="button" className="cursor-pointer underline" onClick={onNew}>
            Make the first one.
          </button>
        </Card>
      ) : (
        <>
          <Tabs agents={agents} filter={filter} onFilter={setFilter} />
          <Card>
            {shown.length === 0 ? (
              <p className="m-0 px-3 py-6 text-center text-sm text-muted">
                No agent is recorded as {WORD[filter]}.
              </p>
            ) : (
              shown.map((listed) => (
                <AgentRow
                  key={listed.key}
                  agent={listed.agent}
                  current={listed.key === current}
                  onOpen={(): void => {
                    onOpen(listed.key);
                  }}
                />
              ))
            )}
          </Card>
        </>
      )}
    </>
  );
}

/** The four the operator named. `all` is not a status; it is the absence of one. */
type Filter = "all" | AgentStatus;

const TABS: readonly Filter[] = ["all", "active", "paused", "error"];

const WORD: Readonly<Record<Filter, string>> = {
  all: "anything",
  active: "active",
  idle: "idle",
  paused: "paused",
  error: "in error",
};

function matches(listed: ListedAgent, filter: Filter): boolean {
  return filter === "all" || listed.agent.status === filter;
}

/**
 * The filters, each carrying how many it would show.
 *
 * The count is on the tab on purpose: every agent in this company has no
 * recorded state at all, so three of these four are empty, and an operator
 * should be able to see that without clicking each one to find out.
 */
function Tabs({
  agents,
  filter,
  onFilter,
}: {
  readonly agents: readonly ListedAgent[];
  readonly filter: Filter;
  readonly onFilter: (filter: Filter) => void;
}): ReactElement {
  return (
    <div role="tablist" aria-label="Agents" className="mb-3 flex gap-1 border-b border-line">
      {TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          aria-selected={tab === filter}
          onClick={(): void => {
            onFilter(tab);
          }}
          className={cn(
            "-mb-px cursor-pointer border-b-2 px-3 py-1.5 text-sm",
            tab === filter
              ? "border-amber font-semibold text-fg"
              : "border-transparent text-muted hover:text-fg"
          )}
        >
          <span className="capitalize">{tab}</span>{" "}
          <span className="text-2xs text-muted">
            {agents.filter((listed) => matches(listed, tab)).length}
          </span>
        </button>
      ))}
    </div>
  );
}

/**
 * How many there are, and the one line about what the record does not keep.
 *
 * D9: the fact renders and the reason sits behind the disclosure a keyboard can
 * reach. The line itself is the fact — three of a row's five columns are empty
 * for every agent in every company, and an operator who is not told that will
 * read it as this company being badly set up.
 */
function Counted({ agents }: { readonly agents: readonly ListedAgent[] }): ReactElement {
  return (
    <>
      <span>
        {agents.length} {agents.length === 1 ? "agent" : "agents"}
      </span>
      {agents.length === 0 ? null : (
        <span className="flex items-center gap-1.5">
          <span>No job title, model or run time is recorded against an agent.</span>
          <Hint text="A persona records a name, and a profile records the harness it runs on. Neither carries a title or a model, and no read ties a recorded run to an agent, so those lines stay empty rather than being filled from something near enough." />
        </span>
      )}
    </>
  );
}
