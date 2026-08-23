import { useEffect, useState } from "react";
import type { TicketSession } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * What each project's crews are actually doing, asked one project at a time.
 *
 * Per project rather than once, because the answers are independent facts: a
 * project whose read did not come back must not take a project whose read did
 * down with it. The pane then shows one project's work and says nothing about
 * the other's, which is the truth.
 *
 * The read is `listProjectSessions` — the one operation in the authored
 * contract that returns a crew's recorded work. It is asked once per mount and
 * not polled: nothing on this surface receives new facts on its own yet, and a
 * page that is not receiving new facts is perfectly still.
 */
export type SessionsByProject = ReadonlyMap<string, Answer<readonly TicketSession[]>>;

/**
 * A project key matches `^[a-z][a-z0-9-]{2,63}$`, so a comma cannot occur in
 * one and the joined form is an exact identity for the set being read.
 */
const SEPARATOR = ",";

export function useSessions(projectKeys: readonly string[]): SessionsByProject {
  const [byProject, setByProject] = useState<SessionsByProject>(new Map());
  // A caller's array is a new object on every render; its contents are what the
  // reads are keyed on, so that is what the effect depends on.
  const identity = projectKeys.join(SEPARATOR);

  useEffect(() => {
    let live = true;
    const keys = identity === "" ? [] : identity.split(SEPARATOR);
    setByProject(new Map(keys.map((key) => [key, ASKING])));
    const load = async (key: string): Promise<void> => {
      const answer = await ask(() => reads.listProjectSessions({ projectKey: key }));
      if (!live) {
        return;
      }
      setByProject((current) => new Map(current).set(key, sessionsOf(answer)));
    };
    for (const key of keys) {
      void load(key);
    }
    return (): void => {
      live = false;
    };
  }, [identity]);

  return byProject;
}

/**
 * One project's recorded sessions, in the record's own order — and only ever a
 * project's.
 *
 * The session page read is a record-position cursor page (`ORDER BY
 * event.record_position`), so the answer arrives ordered by the record;
 * re-sorting it by `started_at` here would overrule that with a string
 * comparison the record never declared. There is deliberately no per-crew read
 * here, because the authored contract has no key that joins one. A bundle
 * assignment carries `component`, `slot` and `subject` and nothing else; a
 * session carries `seat_key` and `crew_name`, which SPEC keeps as authored
 * strings distinct from an assignment's subject. Filtering sessions by a
 * crew's subject would therefore be a guess wearing the clothes of a fact, and
 * a rail full of quietly wrong marks is worse than a rail with none.
 * `project_key` is the one key both sides really share.
 */
export function sessionsOfProject(
  answer: Answer<readonly TicketSession[]> | undefined
): Answer<readonly TicketSession[]> {
  return answer ?? ASKING;
}

function sessionsOf(
  answer: Answer<{ readonly sessions: readonly TicketSession[] }>
): Answer<readonly TicketSession[]> {
  return answer.kind === "answered" ? { kind: "answered", value: answer.value.sessions } : answer;
}
