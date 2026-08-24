import type { ReactElement } from "react";
import { Chip } from "../ui/primitives";
import { Mark } from "../ui/marks";
import { cn } from "../ui/cn";
import { stamp } from "../inbox/when";
import { standingOf } from "./status";
import type { AgentFacts } from "./read";

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
 *
 * The row carries no "this is the one you asked for" state. Naming an agent —
 * here or in the rail — opens that agent's own home, so a highlighted row in a
 * list nobody is looking at would be a state the operator can never see.
 */
export function AgentRow({
  agent,
  onOpen,
}: {
  readonly agent: AgentFacts;
  readonly onOpen: (agent: AgentFacts) => void;
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
        {agent.role === null ? null : (
          <span className="block truncate text-xs text-muted">{agent.role}</span>
        )}
      </span>
      <Runs agent={agent} />
      <Chip tone={standing.tone}>{standing.word}</Chip>
    </button>
  );
}

/**
 * What it runs on and when it last ran — the two facts that answer "is this
 * thing working for me", side by side and quiet.
 *
 * Each is drawn only where there is one to draw. A record that keeps no model
 * gets no model, and a record that ties no run to an agent gets no time: the
 * screen says once, in a line of its own, which of these it is short of.
 * "Never run" would be an answer, and nothing here has asked the question.
 */
function Runs({ agent }: { readonly agent: AgentFacts }): ReactElement {
  const runs = [agent.model, agent.harness].filter((one) => one !== null);
  return (
    <span className="hidden min-w-0 shrink-0 text-right sm:block">
      {runs.length === 0 ? null : (
        <span className="block truncate text-xs">{runs.join(" · ")}</span>
      )}
      {agent.lastActive === null ? null : (
        <span className="block text-2xs text-muted" title={agent.lastActive}>
          {stamp(agent.lastActive)}
        </span>
      )}
    </span>
  );
}
