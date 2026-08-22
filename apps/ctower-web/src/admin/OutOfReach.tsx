import type { ReactElement } from "react";
import { Hint } from "../ui/form";
import { Card, CardBody, CardHeader, CardTitle } from "../ui/primitives";

/**
 * The four console jobs this console cannot do, and why — stated, not hidden.
 *
 * A destination the operator cannot see is one they assume works. `DESIGN.md`
 * keeps unbuilt destinations in the rail for exactly that reason, and the same
 * argument holds one level down: an Admin screen that showed only the job it
 * can do would read as the whole of console access.
 *
 * No mark is drawn on any of these. The six glyphs are the CLI's state
 * vocabulary and none of them means "out of reach" — `⛔` means the tower
 * refused, and the tower has not been asked. Unknown draws nothing.
 */
interface Job {
  readonly job: string;
  readonly reason: string;
  readonly why: string;
}

const ELSEWHERE =
  "The tower serves this to the private console window, on that window's own " +
  "origin and its own proof. This console holds the operator credential instead, " +
  "which is not that proof.";

const UNBUILT =
  "The authored contract declares this operation but keeps it out of the " +
  "generated client, so no call to it exists in this build. Reaching it is a " +
  "contract change, not a screen.";

const JOBS: readonly Job[] = [
  { job: "See what is being watched", reason: "Private console window", why: ELSEWHERE },
  { job: "Open a terminal", reason: "Private console window", why: ELSEWHERE },
  { job: "Stop a watch", reason: "Not in this client", why: UNBUILT },
  { job: "Turn watching off everywhere", reason: "Not in this client", why: UNBUILT },
];

export function OutOfReach(): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Not reachable from here</CardTitle>
      </CardHeader>
      <CardBody className="p-0">
        <ul className="m-0 list-none p-0">
          {JOBS.map((entry) => (
            <li
              key={entry.job}
              className="flex items-center gap-3 border-b border-line px-4 py-2 text-sm last:border-b-0"
            >
              <span className="min-w-0 flex-1 truncate text-muted">{entry.job}</span>
              <span className="shrink-0 text-2xs text-muted">{entry.reason}</span>
              <Hint text={entry.why} />
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}
