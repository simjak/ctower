import { useEffect, useState } from "react";
import type { AssignmentList, TicketSessionList } from "@ctower/client";
import { ask, ASKING, reads } from "../../api/client";
import type { Answer } from "../../api/client";

/**
 * What the record says about the crew on one ticket.
 *
 * Two reads, kept apart on purpose. `listTicketSessions` answers "who is working
 * this, and on what" and `listTicketAssignments` answers "who holds it" — they
 * are different facts recorded by different acts, and a ticket can easily have
 * one and not the other. Folding them into a single answer would make an
 * unreachable read look like an absent crew, so each keeps its own outcome and
 * the screen says which one it is missing.
 *
 * Both are asked once per ticket and not polled. Nothing on this surface
 * receives new facts on its own, and `DESIGN.md` is explicit that a page which
 * is not receiving new facts is perfectly still.
 */
export interface TicketCrewReads {
  readonly sessions: Answer<TicketSessionList>;
  readonly assignments: Answer<AssignmentList>;
}

export function useTicketCrew(projectKey: string, ticketId: string): TicketCrewReads {
  const [held, setHeld] = useState<TicketCrewReads>({ sessions: ASKING, assignments: ASKING });

  useEffect(() => {
    let live = true;
    setHeld({ sessions: ASKING, assignments: ASKING });
    const readSessions = async (): Promise<void> => {
      const sessions = await ask(() => reads.listTicketSessions({ projectKey, ticketId }));
      if (live) {
        setHeld((current) => ({ ...current, sessions }));
      }
    };
    const readAssignments = async (): Promise<void> => {
      const assignments = await ask(() => reads.listTicketAssignments({ projectKey, ticketId }));
      if (live) {
        setHeld((current) => ({ ...current, assignments }));
      }
    };
    void readSessions();
    void readAssignments();
    return (): void => {
      live = false;
    };
  }, [projectKey, ticketId]);

  return held;
}
