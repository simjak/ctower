import { useEffect, useState } from "react";
import type { BoardView, TicketResource, TimelineResponse } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * The board read, and the ticket read behind a card.
 *
 * Both are `GET`s asked once per subject, and neither polls. `DESIGN.md`
 * reserves motion for real work moving; a board that repaints itself on a timer
 * is a screen that moves when nothing has, and it would also make every
 * screenshot of it a different screenshot. New facts arrive when the operator
 * asks for them.
 */
export function useBoard(projectKey: string | null, reloadKey: number): Answer<BoardView> {
  const [board, setBoard] = useState<Answer<BoardView>>(ASKING);

  useEffect(() => {
    if (projectKey === null) {
      return;
    }
    let live = true;
    setBoard(ASKING);
    const load = async (): Promise<void> => {
      const answer = await ask(() => reads.getBoard({ projectKey }));
      if (live) {
        setBoard(answer);
      }
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [projectKey, reloadKey]);

  return board;
}

/** What a card's detail is made of: the ticket itself, and its recorded history. */
export interface TicketReads {
  readonly ticket: Answer<TicketResource>;
  readonly timeline: Answer<TimelineResponse>;
}

export function useTicket(projectKey: string, ticketId: string): TicketReads {
  const [ticket, setTicket] = useState<Answer<TicketResource>>(ASKING);
  const [timeline, setTimeline] = useState<Answer<TimelineResponse>>(ASKING);

  useEffect(() => {
    let live = true;
    setTicket(ASKING);
    setTimeline(ASKING);
    const load = async (): Promise<void> => {
      const [read, history] = await Promise.all([
        ask(() => reads.getTicket({ projectKey, ticketId })),
        ask(() => reads.getTicketTimeline({ projectKey, ticketId })),
      ]);
      if (live) {
        setTicket(read);
        setTimeline(history);
      }
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [projectKey, ticketId]);

  return { ticket, timeline };
}
