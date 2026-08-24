import type { ReactElement } from "react";
import { Chip } from "../../ui/primitives";
import { Mark } from "../../ui/marks";
import { cn } from "../../ui/cn";
import { stamp } from "../../inbox/when";
import { readingOf, spend } from "./crew";
import type { Crew } from "./crew";

/**
 * One crew, the way the operator already reads his fleet.
 *
 * The order across the row is the order he asks in: is it working, who is it,
 * what is it running on, what has it spent, when did it last move. Nothing here
 * is a key, a revision or a reference — a crew is a member of staff on this
 * screen and the record's addressing is the wiring's business.
 *
 * A column with nothing recorded draws NOTHING. No dash, no "n/a", no borrowed
 * mark: a dash is a value, and a row full of placeholder dashes is exactly the
 * dead screen this design replaces.
 */
export function CrewRow({
  crew,
  onOpen,
}: {
  readonly crew: Crew;
  readonly onOpen: (crew: Crew) => void;
}): ReactElement {
  const reading = readingOf(crew.standing);
  return (
    <button
      type="button"
      onClick={(): void => {
        onOpen(crew);
      }}
      className={cn(
        "flex w-full cursor-pointer items-center gap-3 border-b border-line px-3 py-2.5",
        "text-left last:border-b-0 hover:bg-raised"
      )}
    >
      {reading.mark === null ? (
        <span className="w-[1.4em] shrink-0" />
      ) : (
        <Mark name={reading.mark} />
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold">{crew.name}</span>
        {crew.role === null ? null : (
          <span className="block truncate text-xs text-muted">{crew.role}</span>
        )}
      </span>
      <Runs crew={crew} />
      <Spend tokens={crew.tokens} />
      <Chip tone={reading.tone}>{reading.word}</Chip>
    </button>
  );
}

/**
 * What it runs on and when it last moved.
 *
 * The harness comes off the crew's own profile and is always there. The model
 * does not: an agent profile records a persona, a harness, skills and tools, and
 * no model at all, so the only model this console can name is one a recorded run
 * served. A crew no run names gets its harness and nothing after it.
 */
function Runs({ crew }: { readonly crew: Crew }): ReactElement {
  const runs = [crew.harness, crew.model].filter((one) => one !== null);
  return (
    <span className="hidden min-w-0 shrink-0 text-right sm:block sm:w-[196px]">
      {runs.length === 0 ? null : (
        <span className="block truncate text-xs">{runs.join(" · ")}</span>
      )}
      {crew.lastActive === null ? null : (
        <span className="block text-2xs text-muted" title={crew.lastActive}>
          {stamp(crew.lastActive)}
        </span>
      )}
    </span>
  );
}

/** What the run spent, when a run is attributable to this crew at all. */
function Spend({ tokens }: { readonly tokens: number | null }): ReactElement {
  return (
    <span className="hidden w-[72px] shrink-0 text-right text-xs tabular-nums md:block">
      {tokens === null ? null : (
        <span title={`${tokens.toLocaleString()} tokens`}>{spend(tokens)}</span>
      )}
    </span>
  );
}
