import type { ReactElement } from "react";

/**
 * What an agent holds out of the company's own catalogue — its skills, its
 * tools — listed by the name a person gave each one.
 *
 * A profile pins these by reference and the bundle records a display name for
 * each; a reference nothing answers is dropped upstream rather than printed, so
 * everything on this list is something the company can actually name. Choosing
 * among them is a write this screen does not make yet, and it does not draw a
 * control that would suggest otherwise.
 */
export function Held({
  what,
  held,
  reason,
}: {
  /** The plural noun, for the empty line: "skills", "tools". */
  readonly what: string;
  readonly held: readonly string[];
  /** Why the list is empty, when it is. */
  readonly reason: string;
}): ReactElement {
  if (held.length === 0) {
    return (
      <div className="grid place-content-center rounded-md border border-line bg-card p-10 text-center">
        <p className="m-0 text-sm text-muted">This agent holds no {what}.</p>
        <p className="mt-1 mb-0 max-w-[46ch] text-xs text-balance text-muted">{reason}</p>
      </div>
    );
  }
  return (
    <ul className="m-0 list-none rounded-md border border-line bg-card p-0">
      {held.map((name) => (
        <li key={name} className="border-b border-line px-4 py-2.5 text-sm last:border-b-0">
          {name}
        </li>
      ))}
    </ul>
  );
}
