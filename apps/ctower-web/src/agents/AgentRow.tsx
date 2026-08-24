import type { ReactElement } from "react";
import { Chip } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { cn } from "../ui/cn";
import { stamp } from "../inbox/when";
import { standingOf } from "./status";
import type { AgentStatus } from "./status";

/**
 * One agent, as a person would introduce them.
 *
 * Every word in this row is one the operator already says: a name, a job, the
 * model, the harness, when it last did something. No key, no revision, no
 * digest — an agent is a member of staff on this screen, and the record's
 * addressing is the wiring's business, derived from the row rather than printed
 * on it.
 *
 * The stamp is absolute on purpose. `when.ts` settled it for the inbox: a
 * relative time goes stale on a page that is still by design and cannot be
 * compared against the CLI or a log, so this prints the sortable instant in the
 * reader's own zone and keeps the exact recorded value on `title`.
 */
export interface Agent {
  readonly name: string;
  /** The job, in the operator's words: "Chief of staff · CEO". */
  readonly role: string;
  /** Plain product names, both of them: "claude-fable-5", "Claude Code". */
  readonly model: string;
  readonly harness: string;
  /** When this agent last did something, or nothing recorded yet. */
  readonly lastActive: string | null;
  /** The recorded state, or nothing recorded yet. */
  readonly status: AgentStatus | null;
}

export function AgentRow({
  agent,
  onOpen,
}: {
  readonly agent: Agent;
  readonly onOpen: (agent: Agent) => void;
}): ReactElement {
  const standing = standingOf(agent.status);
  return (
    <button
      type="button"
      onClick={(): void => {
        onOpen(agent);
      }}
      className={cn(
        "flex w-full cursor-pointer items-center gap-3 border-b border-line px-3 py-2.5",
        "text-left last:border-b-0 hover:bg-raised"
      )}
    >
      {standing.mark === null ? (
        <span className="w-[1.4em] shrink-0" />
      ) : (
        <Mark name={standing.mark} />
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{agent.name}</span>
        <span className="block truncate text-xs text-muted">{agent.role}</span>
      </span>
      <Runs agent={agent} />
      <Chip tone={standing.tone}>{standing.word}</Chip>
    </button>
  );
}

/**
 * What it runs on and when it last ran — the two facts that answer "is this
 * thing working for me", side by side and quiet.
 */
function Runs({ agent }: { readonly agent: Agent }): ReactElement {
  return (
    <span className="hidden min-w-0 shrink-0 text-right sm:block">
      <span className="block truncate text-xs">
        {agent.model} · {agent.harness}
      </span>
      {agent.lastActive === null ? (
        <span className="block text-2xs text-muted">never run</span>
      ) : (
        <span className="block text-2xs text-muted" title={agent.lastActive}>
          {stamp(agent.lastActive)}
        </span>
      )}
    </span>
  );
}
