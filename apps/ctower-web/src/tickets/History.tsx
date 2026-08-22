import type { ReactElement } from "react";
import type { TimelineResponse } from "@ctower/client";
import { Hint } from "../ui/form";
import { Card, CardBody, CardHeader, CardTitle, Mono } from "../ui/primitives";
import { Instant } from "./facts";
import { historyOf, HISTORY_SCOPE } from "./history";

/**
 * What has happened to this ticket, oldest first.
 *
 * The section states its own scope behind a focusable `(i)`, because the
 * timeline read carries four event kinds and a heading of "History" over a
 * partial stream would read as "nothing else happened".
 */
export function History({ timeline }: { readonly timeline: TimelineResponse }): ReactElement {
  const entries = historyOf(timeline.events);
  return (
    <Card>
      <CardHeader>
        <CardTitle>History</CardTitle>
        <Hint text={HISTORY_SCOPE} />
        <span className="flex-1" />
        <Mono className="text-muted">{entries.length}</Mono>
      </CardHeader>
      <CardBody className="py-1">
        <ol className="m-0 list-none p-0">
          {entries.map((entry) => (
            <li
              key={entry.id}
              className="flex items-baseline gap-3 border-b border-line py-2 last:border-b-0"
            >
              <Instant at={entry.at} />
              <span className="w-36 shrink-0 text-sm font-medium">{entry.what}</span>
              <span className="min-w-0 flex-1 text-sm break-words">
                {entry.detail === null ? null : entry.machine ? (
                  <Mono>{entry.detail}</Mono>
                ) : (
                  entry.detail
                )}
              </span>
              <Mono className="hidden shrink-0 text-muted md:inline" title={entry.actor}>
                {entry.actor.slice(0, 8)}
              </Mono>
            </li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}
