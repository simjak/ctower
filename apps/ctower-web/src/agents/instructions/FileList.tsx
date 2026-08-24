import type { ReactElement } from "react";
import { cn } from "../../ui/cn";
import { Card, CardBody, CardHeader, CardTitle, Chip } from "../../ui/primitives";
import type { AgentFile, Role } from "./agent";

/**
 * What this agent reads, as a person would list it.
 *
 * The old harness version of this list carried three machine values on every
 * row — the component key, `r` and a revision, and a shortened digest — which
 * is three of AC-7's banned families stacked on the one surface an operator
 * opens most. None of them survived the move. What identifies a file to a
 * person is its name; what identifies it to the record is in the Advanced
 * disclosure of whatever is open, which is where the operator goes when they
 * need to carry an address somewhere else.
 *
 * The entry wears a badge and nothing else does. `persona_ref` is a single
 * field naming a single component and the profile has no second one, so "which
 * of these is the agent itself" is a fact the record already answers — the
 * badge just says it out loud, in one word, the way the reference console marks
 * its own entry file.
 *
 * No mark is drawn on any row. The six glyphs are execution states and a file
 * has none: it was never started, so it never finished, and borrowing the
 * neighbouring glyph is how a document gets rendered as a run.
 */
const GROUPS: readonly { readonly role: Role; readonly title: string }[] = [
  { role: "entry", title: "Who it is" },
  { role: "skill", title: "What it can do" },
  { role: "tool", title: "What it may reach" },
];

export function FileList({
  files,
  openId,
  onOpen,
}: {
  readonly files: readonly AgentFile[];
  readonly openId: string | null;
  readonly onOpen: (id: string) => void;
}): ReactElement {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle>Files</CardTitle>
      </CardHeader>
      <CardBody className="space-y-3 p-1.5">
        {GROUPS.map((group) => {
          const held = files.filter((entry) => entry.role === group.role);
          return held.length === 0 ? null : (
            <section key={group.role}>
              <h3 className="mx-2.5 mt-1 mb-1.5 p-0 text-[10.5px] tracking-[0.1em] text-muted uppercase">
                {group.title}
              </h3>
              {held.map((entry) => (
                <Row key={entry.id} entry={entry} open={entry.id === openId} onOpen={onOpen} />
              ))}
            </section>
          );
        })}
      </CardBody>
    </Card>
  );
}

function Row({
  entry,
  open,
  onOpen,
}: {
  readonly entry: AgentFile;
  readonly open: boolean;
  readonly onOpen: (id: string) => void;
}): ReactElement {
  return (
    <button
      type="button"
      aria-current={open}
      onClick={(): void => {
        onOpen(entry.id);
      }}
      className={cn(
        "flex w-full cursor-pointer items-center gap-2 rounded-sm border-l-2 px-2.5 py-2 text-left",
        open ? "border-amber bg-raised" : "border-transparent hover:bg-raised"
      )}
    >
      <span className="min-w-0 flex-1 truncate text-sm font-medium">{entry.name}</span>
      {entry.role === "entry" ? <Chip tone="amber">Entry</Chip> : null}
    </button>
  );
}
