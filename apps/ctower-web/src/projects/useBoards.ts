import { useEffect, useState } from "react";
import type { BoardView } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * One board read per project, and each one answers for itself.
 *
 * The API has no portfolio board — `getBoard` takes exactly one project — so a
 * page showing three projects asks three times. They are kept apart rather than
 * gathered into one state because they are three separate facts: a project whose
 * board refuses says so on its own row, beside two projects that answered, and
 * neither borrows the other's outcome.
 *
 * The reads are started together and land as they land. Nothing here waits for
 * the slowest.
 */
export function useBoards(keys: readonly string[]): ReadonlyMap<string, Answer<BoardView>> {
  const [answers, setAnswers] = useState<ReadonlyMap<string, Answer<BoardView>>>(new Map());
  // The list of projects comes from an already-answered bundle, so it changes
  // only when that document does. Its identity does not survive a render, and
  // its contents do.
  const wanted = keys.join(" ");

  useEffect(() => {
    let live = true;
    const projects = wanted === "" ? [] : wanted.split(" ");
    setAnswers(new Map(projects.map((key) => [key, ASKING])));
    const record = (key: string, answer: Answer<BoardView>): void => {
      if (live) {
        setAnswers((held) => new Map(held).set(key, answer));
      }
    };
    for (const key of projects) {
      void ask(() => reads.getBoard({ projectKey: key })).then((answer) => {
        record(key, answer);
      });
    }
    return (): void => {
      live = false;
    };
  }, [wanted]);

  return answers;
}
