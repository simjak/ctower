import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import type { ListedAgent } from "./read";

/** How many names the rail carries before the rest live behind "See all". */
const SHOWN = 6;

/**
 * The company's agents, by name, in the rail.
 *
 * The operator asked for staff in the sidebar rather than a screen he has to
 * remember to open: each agent listed by the name it speaks under, and one way
 * to the whole list. So this is a section of the rail and not a link in it —
 * the section IS the destination, and "See all agents" is the way to its page.
 *
 * A long payroll does not become a long rail. Six names, then the rest behind
 * "See all", and the count travels with it so the cap is visible rather than
 * silent — a rail that quietly stopped at six would be a rail that lies about
 * how many people work here.
 */
export function AgentsRail({
  agents,
  here,
  current,
  onOpen,
  onSeeAll,
}: {
  readonly agents: readonly ListedAgent[];
  /** Whether the operator is on the agents page at all. */
  readonly here: boolean;
  /** The agent that page is pointed at, when it is pointed at one. */
  readonly current: string | null;
  readonly onOpen: (key: string) => void;
  readonly onSeeAll: () => void;
}): ReactElement {
  const shown = agents.slice(0, SHOWN);
  const hidden = agents.length - shown.length;
  return (
    <div>
      <div className="px-4 pt-3 pb-1 text-[10.5px] tracking-[0.1em] text-muted">AGENTS</div>
      {agents.length === 0 ? (
        <p className="m-0 px-4 pb-1 text-xs text-muted">No agent yet.</p>
      ) : (
        shown.map((listed) => (
          <Entry
            key={listed.key}
            name={listed.agent.name}
            here={here && listed.key === current}
            onOpen={(): void => {
              onOpen(listed.key);
            }}
          />
        ))
      )}
      <Entry
        name={hidden > 0 ? `See all agents (${String(agents.length)})` : "See all agents"}
        here={here && current === null}
        quiet
        onOpen={onSeeAll}
      />
    </div>
  );
}

/**
 * One row of the section, wearing the rail's own three states.
 *
 * It is a plain button rather than the rail's `RailLink` because nothing here
 * is a destination: these rows all lead to one screen, and which agent it opens
 * on is a place inside it.
 */
function Entry({
  name,
  here,
  quiet = false,
  onOpen,
}: {
  readonly name: string;
  readonly here: boolean;
  /** "See all" is a way out of the section, not a member of it. */
  readonly quiet?: boolean;
  readonly onOpen: () => void;
}): ReactElement {
  return (
    <button
      type="button"
      aria-current={here ? "page" : undefined}
      onClick={onOpen}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 py-1.5 pr-4 pl-4 text-left text-sm",
        here
          ? "border-r-2 border-amber bg-amber/14 font-semibold"
          : "border-r-2 border-transparent hover:bg-raised",
        quiet ? "text-muted" : "text-fg"
      )}
    >
      {quiet ? null : (
        <span
          aria-hidden
          className={cn("size-[5px] shrink-0 rounded-full", here ? "bg-amber" : "bg-muted/50")}
        />
      )}
      <span className={cn("truncate", quiet && "text-xs")}>{name}</span>
    </button>
  );
}
