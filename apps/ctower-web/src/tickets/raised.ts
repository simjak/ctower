import { useEffect, useState } from "react";
import { ask, reads } from "../api/client";

/**
 * When each ticket on this project was raised.
 *
 * The board answers a card's lane, title and number, and nothing about time.
 * The one declared read that carries a ticket's raising is the project's own
 * event feed: `ticket.created` names the ticket and the instant together. So
 * the list asks for the feed and keeps that one fact from it.
 *
 * Which ticket an event belongs to is the envelope's own stream, and the join
 * is the authored contract's rather than this console's guess:
 * `contracts/domain/events/event-envelope.schema.json` fixes a ticket event's
 * `stream_id` to `ticket:` followed by the ticket's identifier, on the variant
 * `ticket.created` itself.
 *
 * The feed is paged and ordered by the record's own position, oldest first, so
 * the newest ticket's raising is on the last page rather than the first. Every
 * page is therefore walked. The walk stops at a cap, because a read that would
 * make a screen open in proportion to a project's whole history is not a read a
 * list can make: a ticket the walk did not reach keeps no raised-at, renders no
 * age, and sits under a band that says so. An unknown is drawn as an unknown.
 */
export interface Raisings {
  /** Ticket id to the instant its `ticket.created` event was recorded. */
  readonly at: ReadonlyMap<string, string>;
  /** Whether the whole feed was read. False when the cap stopped the walk. */
  readonly whole: boolean;
}

const PAGE = 100;

/** Twenty pages of a project's history. Two thousand events is a long project. */
const CAP = 20;

const NOTHING: Raisings = { at: new Map(), whole: false };

export function useRaisings(projectKey: string, reloadKey: number): Raisings {
  const [raisings, setRaisings] = useState<Raisings>(NOTHING);

  useEffect((): (() => void) => {
    let live = true;
    setRaisings(NOTHING);
    const load = async (): Promise<void> => {
      const walked = await walk(projectKey);
      if (!live) {
        return;
      }
      setRaisings(walked);
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [projectKey, reloadKey]);

  return raisings;
}

/**
 * The feed, page by page, keeping only what raised a ticket.
 *
 * A page that does not answer ends the walk rather than failing the screen: the
 * list is the board's answer and this is one column of it, so a feed that
 * refuses costs the ages and never the tickets.
 */
async function walk(projectKey: string): Promise<Raisings> {
  const at = new Map<string, string>();
  let cursor = 0;
  for (let page = 0; page < CAP; page += 1) {
    const answer = await ask(() => reads.listProjectEvents({ projectKey, cursor, limit: PAGE }));
    if (answer.kind !== "answered") {
      return { at, whole: false };
    }
    for (const event of answer.value.events) {
      if (event.kind === "ticket.created") {
        at.set(event.stream_id.slice("ticket:".length), event.occurred_at);
      }
    }
    const next = answer.value.next_cursor;
    if (next === null) {
      return { at, whole: true };
    }
    cursor = next;
  }
  return { at, whole: false };
}
