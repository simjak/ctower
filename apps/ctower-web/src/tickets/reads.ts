import { useEffect, useState } from "react";
import type { BoardView, TicketResource, TimelineResponse } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * The two reads this page is built from, and nothing behind them.
 *
 * The list is `getBoard`: it is the only operation the authored contract
 * declares that answers with more than one ticket. One ticket is `getTicket`
 * plus `getTicketTimeline`, asked together because a stage move needs facts
 * from both and a page that showed one without the other could offer a move it
 * cannot describe.
 */
export function useBoard(projectKey: string | null, reloadKey: number): Answer<BoardView> {
  const [board, setBoard] = useState<Answer<BoardView>>(ASKING);

  useEffect((): (() => void) => {
    if (projectKey === null) {
      return (): void => undefined;
    }
    let live = true;
    setBoard(ASKING);
    const load = async (): Promise<void> => {
      const answer = await ask(() => reads.getBoard({ projectKey }));
      if (!live) {
        return;
      }
      setBoard(answer);
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [projectKey, reloadKey]);

  return board;
}

export interface OneTicket {
  readonly ticket: TicketResource;
  readonly timeline: TimelineResponse;
}

export function useTicket(
  projectKey: string,
  ticketId: string,
  reloadKey: number
): Answer<OneTicket> {
  const [one, setOne] = useState<Answer<OneTicket>>(ASKING);

  useEffect((): (() => void) => {
    let live = true;
    setOne(ASKING);
    const load = async (): Promise<void> => {
      const answer = await bothReads(projectKey, ticketId);
      if (!live) {
        return;
      }
      setOne(answer);
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [projectKey, ticketId, reloadKey]);

  return one;
}

/** Ask for the ticket and its history, and stop at the first thing that is not an answer. */
async function bothReads(projectKey: string, ticketId: string): Promise<Answer<OneTicket>> {
  const ticket = await ask(() => reads.getTicket({ projectKey, ticketId }));
  if (ticket.kind !== "answered") {
    return ticket;
  }
  const timeline = await ask(() => reads.getTicketTimeline({ projectKey, ticketId }));
  if (timeline.kind !== "answered") {
    return timeline;
  }
  return { kind: "answered", value: { ticket: ticket.value, timeline: timeline.value } };
}
