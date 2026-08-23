import { useEffect, useRef, useState } from "react";
import type { MovementEvent } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";
import { movedSince, positionOf } from "./conveyor";
import type { Moved } from "./conveyor";

/**
 * The moves this project has recorded, and which of them are new to this
 * screen.
 *
 * `listTicketMovement` is the record's own account of work moving: one event
 * per accepted transition, carrying the stage it left, the stage it entered,
 * and a monotonic position in the stream. That position is what "new" means
 * here. The screen holds the highest one it has drawn, and a re-read that folds
 * nothing past it produces no moves at all — which is why a still board stays
 * still.
 *
 * It does not poll, for the reason the board does not: a surface that re-asks
 * on a timer moves when nothing has. It reads when the project changes and when
 * the operator asks again.
 */
export interface Movement {
  readonly answer: Answer<readonly MovementEvent[]>;
  /** The moves recorded since the last read this screen drew. */
  readonly moved: readonly Moved[];
}

const PAGE = 100;

export function useMovement(projectKey: string | null, reloadKey: number): Movement {
  const [answer, setAnswer] = useState<Answer<readonly MovementEvent[]>>(ASKING);
  const [moved, setMoved] = useState<readonly Moved[]>([]);
  // The position the previous read ended at. A ref, not state: it is what the
  // next read is measured against and must not itself cause one.
  const seen = useRef<number | null>(null);

  useEffect(() => {
    if (projectKey === null) {
      return;
    }
    let live = true;
    setAnswer(ASKING);
    const load = async (): Promise<void> => {
      const page = await ask(() => reads.listTicketMovement({ projectKey, limit: PAGE }));
      if (!live) {
        return;
      }
      if (page.kind !== "answered") {
        // A movement read that did not answer says nothing about movement, so
        // nothing animates and the position stands where it was.
        setAnswer(page);
        setMoved([]);
        return;
      }
      const events = page.value.events;
      setAnswer({ kind: "answered", value: events });
      setMoved(movedSince(events, seen.current));
      seen.current = positionOf(events) ?? seen.current;
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [projectKey, reloadKey]);

  // A project change is not movement: the first read of a project draws its
  // cards where they stand rather than sliding them in from nowhere.
  useEffect(() => {
    seen.current = null;
    setMoved([]);
  }, [projectKey]);

  return { answer, moved };
}
