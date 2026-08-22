import { useEffect, useState } from "react";
import type { RequestList } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * The one read this screen is built on.
 *
 * `listRequests` takes a single optional parameter — the project — so the scope
 * control is that parameter and nothing else. There is no client-side filter
 * and no client-side sort: rows arrive in the record's own order, and a screen
 * that re-ranked them locally would be showing an order no one recorded.
 *
 * A scope change re-asks rather than narrowing what is already held, because
 * the answer carries its own epistemics — which projects answered, at which
 * watermark, observed when — and those belong to the scope that produced them.
 */
export function useLedger(project: string | null, reloadKey: number): Answer<RequestList> {
  const [answer, setAnswer] = useState<Answer<RequestList>>(ASKING);

  useEffect(() => {
    let live = true;
    setAnswer(ASKING);
    const load = async (): Promise<void> => {
      const next = await ask(() =>
        reads.listRequests(project === null ? {} : { projectKey: project })
      );
      if (live) {
        setAnswer(next);
      }
    };
    void load();
    return (): void => {
      live = false;
    };
  }, [project, reloadKey]);

  return answer;
}
