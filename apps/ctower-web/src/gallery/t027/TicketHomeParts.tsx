import type { ReactElement } from "react";
import { Card, CardBody, CardHeader, CardTitle } from "../../ui/primitives";
import { Inert } from "../../projects/Inert";
import { Instant } from "../../tickets/facts";

/**
 * The three panels of the operator's factory card that are not the ladder:
 * what has happened, who has held it, and the sections the record cannot fill.
 */

/**
 * What has happened to this ticket.
 *
 * The record answers this one read with nine kinds of event, and each line here
 * is one of them said in the operator's language: it was raised, it changed
 * hands, it moved, someone wrote on it, a crew opened a session on it. No line
 * is derived and none is summarised — the feed says what the record said.
 */
export function Happened(): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>What has happened</CardTitle>
      </CardHeader>
      <CardBody className="py-1">
        {EVENTS.map((event) => (
          <div
            key={event.at}
            className="flex items-baseline gap-3 border-b border-line py-2 last:border-b-0"
          >
            <span className="shrink-0 whitespace-nowrap">
              <Instant at={event.at} />
            </span>
            <span className="min-w-0 flex-1 text-sm">{event.said}</span>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

const EVENTS: readonly { readonly at: string; readonly said: string }[] = [
  { at: "2026-08-24T19:31:00Z", said: "Moved to Design." },
  {
    at: "2026-08-24T19:24:00Z",
    said: "“Five references attached; the create modal is the one to get right first.”",
  },
  { at: "2026-08-24T19:20:00Z", said: "Moved to Plan." },
  { at: "2026-08-24T19:14:00Z", said: "Handed over — the designer takes it from here." },
  { at: "2026-08-24T19:12:00Z", said: "Raised." },
];

/**
 * Who has held this ticket, and for how long.
 *
 * The record answers with an episode per hand-over: which one it is, when it
 * opened, when it closed, and the reason given. It names the person by
 * identifier, and nothing turns that into a name — so the episode is drawn and
 * the person is not, rather than a number being put on screen as if it were
 * somebody.
 */
export function Custody(): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Held by</CardTitle>
      </CardHeader>
      <CardBody className="py-1">
        {EPISODES.map((episode) => (
          <div key={episode.at} className="border-b border-line py-2 last:border-b-0">
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-medium">Episode {episode.number}</span>
              <span className="flex-1" />
              <span className="text-2xs text-muted">{episode.open ? "open" : "closed"}</span>
            </div>
            <p className="mt-0.5 mb-0 text-sm text-muted">{episode.reason}</p>
            <p className="mt-0.5 mb-0">
              <Instant at={episode.at} />
            </p>
          </div>
        ))}
        <p className="mt-1 mb-1 text-2xs text-muted">
          ctower records who each episode belongs to, and nothing here can turn that answer into a
          person's name yet.
        </p>
      </CardBody>
    </Card>
  );
}

const EPISODES: readonly {
  readonly number: number;
  readonly at: string;
  readonly reason: string;
  readonly open: boolean;
}[] = [
  { number: 2, at: "2026-08-24T19:14:00Z", reason: "Design stage, iterating with the operator", open: true },
  { number: 1, at: "2026-08-24T19:12:00Z", reason: "Raised and triaged", open: false },
];

/**
 * The four sections of the operator's card the record cannot answer yet.
 *
 * They stay on the screen, dimmed, each saying why — the same law the rail
 * follows for a destination that does not exist. It matters that they are
 * visible: the operator asked for this card, and the honest report is which
 * parts of it ctower already keeps and which it does not, not a page quietly
 * missing four of nine sections.
 */
export function Unbuilt(): ReactElement {
  return (
    <section aria-label="Not recorded yet">
      <div className="mb-2 text-2xs text-muted">NOT RECORDED YET</div>
      <div className="flex flex-wrap gap-2">
        {MISSING.map((entry) => (
          <Inert
            key={entry.what}
            className="rounded-md border px-3 py-2 text-sm"
            reason={entry.why}
          >
            {entry.what}
          </Inert>
        ))}
      </div>
    </section>
  );
}

const MISSING: readonly { readonly what: string; readonly why: string }[] = [
  {
    what: "Acceptance criteria",
    why: "The record can freeze criteria on a ticket, and no read answers with them, so nothing here can list them.",
  },
  {
    what: "Evidence",
    why: "Evidence is recorded against a ticket, and no read answers with the slots or what fills them.",
  },
  {
    what: "Assets",
    why: "A ticket keeps no attachment, and a browser has nowhere to put one.",
  },
  {
    what: "Metrics",
    why: "Nothing counts a ticket's cost or its time in a stage yet.",
  },
];
