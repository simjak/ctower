import { useEffect, useState } from "react";
import type { ProjectSessionPage } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * What each project's crews are actually doing, asked one project at a time.
 *
 * Per project rather than once, because the answers are independent facts: a
 * project whose read did not come back must not take a project whose read did
 * down with it. The screen then states one project's work and says nothing
 * about the other's, which is the truth.
 *
 * The read is `listProjectSessions` — the one operation in the authored
 * contract that returns a crew's recorded work. It is asked once per mount and
 * not polled: nothing on this surface receives new facts on its own yet, and a
 * page that is not receiving new facts is perfectly still.
 *
 * The **page** is what a caller gets, not the rows inside it. It is a cursor
 * page, so `next_cursor` is the difference between "this is the project's work"
 * and "this is the first hundred of it", and a caller that counts has to know
 * which one it is holding. Dropping the cursor here is how a partial page
 * becomes a total.
 */
export type SessionsByProject = ReadonlyMap<string, Answer<ProjectSessionPage>>;

/**
 * A project key matches `^[a-z][a-z0-9-]{2,63}$`, so a comma cannot occur in
 * one and the joined form is an exact identity for the set being read.
 */
const SEPARATOR = ",";

/**
 * The largest page the contract offers (`AuditLimit`, maximum 100). Asked for
 * in full because a caller that only counts what it was handed is exact when
 * the cursor is spent, and this asks for the widest window in which that
 * happens.
 */
const PAGE = 100;

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
      const answer = await ask(() => reads.listProjectSessions({ projectKey: key, limit: PAGE }));
      if (!live) {
        return;
      }
      setByProject((current) => new Map(current).set(key, answer));
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
 * a screen full of quietly wrong marks is worse than a screen with none.
 * `project_key` is the one key both sides really share.
 */
export function sessionsOfProject(
  answer: Answer<ProjectSessionPage> | undefined
): Answer<ProjectSessionPage> {
  return answer ?? ASKING;
}
