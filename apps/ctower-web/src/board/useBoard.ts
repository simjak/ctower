import { useEffect, useState } from "react";
import type { BoardView, TicketResource } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * The board read, and the ticket read behind a card.
 *
 * Both are `GET`s asked once per subject and neither polls. `DESIGN.md` reserves
 * motion for real work moving; a board that repaints itself on a timer is a
 * screen that moves when nothing has. New facts arrive when the operator asks.
 *
 * `project_key` is a required parameter of the board read, so choosing a project
 * is not a filter over one answer — it is a different answer, at its own
 * watermark. That is why it lives here and the priority filter does not.
 */
export function useBoard(projectKey: string | null): Answer<BoardView> {
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
  }, [projectKey]);

  return board;
}

export function useTicket(projectKey: string, ticketId: string): Answer<TicketResource> {
  const [ticket, setTicket] = useState<Answer<TicketResource>>(ASKING);

  useEffect(() => {
    let live = true;
    setTicket(ASKING);
    const load = async (): Promise<void> => {
      const answer = await ask(() => reads.getTicket({ projectKey, ticketId }));
      if (live) {
        setTicket(answer);
      }
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [projectKey, ticketId]);

  return ticket;
}
