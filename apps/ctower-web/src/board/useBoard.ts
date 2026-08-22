import { useEffect, useState } from "react";
import type { BoardView, TicketResource } from "@ctower/client";
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

/**
 * What only the record knows about a card.
 *
 * This hook used to ask `getTicketTimeline` alongside `getTicket`, and the
 * panel drew both. The audit read answers the timeline's four event kinds and
 * five more, so the timeline read has no question left of its own and is no
 * longer asked — an unread read is a request an operator's tower serves for
 * nothing. The audit read owns the history and lives in `audit/useAudit.ts`,
 * because it pages and this one does not.
 */
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
