import type { ReactElement } from "react";
import type { Answer } from "../api/client";
import { Mark } from "../ui/marks";
import type { MarkName } from "../ui/marks";
import { Asking } from "../wizard/states";

/**
 * Every answer that is not an answer, told in the operator's own words.
 *
 * The four outcomes stay four: ctower said no, ctower said nothing, and ctower
 * said something this screen cannot read are three different facts with three
 * different next moves, and collapsing them into one error box is how an
 * operator loses the ability to tell "it refused" from "it never arrived".
 *
 * What changes here from the wizard's version of the same states is where the
 * machine's own words go. A refusal code, an unmet fact and a decode failure
 * are written for whoever maintains ctower, not for whoever runs it, so they
 * sit closed behind a disclosure that says who it is for — reachable in one
 * keystroke, and never in the operator's way.
 *
 * It says nothing about what was being read, so it is not typed to one read.
 * Every screen under `agents/` meets the same four outcomes and owes the
 * operator the same four sentences; a second copy of them, differing only in
 * its type parameter, is how two screens start disagreeing about what silence
 * means.
 */
export function Waiting({
  answer,
  what = "Reading this team's work",
}: {
  readonly answer: Answer<unknown>;
  /** What is being read, in the operator's words, while it is still out. */
  readonly what?: string;
}): ReactElement | null {
  switch (answer.kind) {
    case "asking":
      return <Asking what={what} />;
    case "answered":
      return null;
    case "refused":
      return (
        <Trouble
          mark="dead"
          said="ctower would not answer this."
          next="Nothing was read. Reload to ask again."
          detail={[
            answer.problem.code,
            answer.problem.detail,
            ...(answer.problem.unmet_facts ?? []),
          ]}
        />
      );
    case "unreachable":
      // No mark. Silence is not a state the record ever recorded, and the
      // vocabulary has no glyph that means "nothing came back".
      return (
        <Trouble
          mark={null}
          said="ctower did not answer."
          next="Reload to ask again."
          detail={[answer.detail]}
        />
      );
    case "malformed":
      return (
        <Trouble
          mark="warn"
          said="ctower answered something this screen cannot read."
          next="Nothing here is wrong with the work. This one is for engineering."
          detail={[answer.detail]}
        />
      );
  }
}

function Trouble({
  mark,
  said,
  next,
  detail,
}: {
  readonly mark: MarkName | null;
  readonly said: string;
  readonly next: string;
  readonly detail: readonly string[];
}): ReactElement {
  return (
    <div className="rounded-md border border-line bg-raised p-3">
      <div className="flex items-start gap-2">
        {mark === null ? null : <Mark name={mark} className="mt-0.5" />}
        <div className="min-w-0 flex-1">
          <p className="m-0 text-sm font-medium text-fg">{said}</p>
          <p className="mt-1.5 mb-0 text-xs text-muted">{next}</p>
          {/* A native disclosure, so a keyboard reaches it without this screen
              teaching one anything, and so it is shut until someone asks. */}
          <details className="mt-2">
            <summary className="cursor-pointer text-2xs text-muted">Developer detail</summary>
            <ul className="mt-1.5 mb-0 list-none space-y-0.5 p-0">
              {detail.map((line) => (
                <li key={line} className="mono break-all text-muted">
                  {line}
                </li>
              ))}
            </ul>
          </details>
        </div>
      </div>
    </div>
  );
}
