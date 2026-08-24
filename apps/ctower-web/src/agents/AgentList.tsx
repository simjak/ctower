import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import type { AgentFacts } from "./roster";

/**
 * The company's agents, one row each — and this is the smallest honest version
 * of that screen, not §2's.
 *
 * **This file is the agents-page lane's to replace.** What §2 asks for beyond
 * this — the filter tabs, "See all agents", the rail's own AGENTS section, and
 * `AgentRow`'s fuller shape — is that lane's work and none of it is here. What
 * is here exists so the agent home has a way in: a junction with no list is a
 * route nobody can walk.
 *
 * It deliberately does not reach for `AgentRow`. That row carries a job title,
 * a model and a last-active stamp, and a recorded agent has none of the three —
 * a persona keeps a name, a profile keeps a harness, and which model ran is a
 * fact of a run rather than a setting on the agent. Filling those slots with
 * empty strings would make the row look answered; leaving the row to the lane
 * that will have the reads for it keeps it whole.
 */
export function AgentList({
  agents,
  onOpen,
}: {
  readonly agents: readonly AgentFacts[];
  readonly onOpen: (key: string) => void;
}): ReactElement {
  if (agents.length === 0) {
    return (
      <p className="m-0 rounded-md border border-line bg-card p-10 text-center text-sm text-muted">
        This company has no agent yet. Make the first one.
      </p>
    );
  }
  return (
    <div className="rounded-md border border-line bg-card">
      {agents.map((agent) => (
        <button
          key={agent.key}
          type="button"
          onClick={(): void => {
            onOpen(agent.key);
          }}
          className={cn(
            "flex w-full cursor-pointer items-center gap-3 border-b border-line px-4 py-2.5",
            "text-left last:border-b-0 hover:bg-raised"
          )}
        >
          <span className="min-w-0 flex-1 truncate text-sm font-semibold">{agent.name}</span>
          {/* No status pill. §2's belongs to the lane that will have a read
              behind it, and a focusable disclosure inside this row's button
              would nest one control inside another. */}
          {agent.harness === null ? null : (
            <span className="shrink-0 text-xs text-muted">{agent.harness}</span>
          )}
        </button>
      ))}
    </div>
  );
}
