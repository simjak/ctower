import { useEffect, useRef, useState } from "react";
import type { DependencyList } from "react";
import type { InboxCorrespondentList, InboxThread, InboxThreadList } from "@ctower/client";
import { ask, ASKING, reads } from "../api/client";
import type { Answer } from "../api/client";

/**
 * The three reads this page is made of, each asked on demand and never on a
 * timer.
 *
 * Stillness is the brand: a page that is not receiving new facts does not move,
 * so nothing here polls. A read is re-asked when the operator asks for it, or
 * when this page has just recorded something that changes the answer — and
 * `reloadKey` is how those two say so.
 *
 * Each read hands back two things, and the difference between them is the whole
 * point. `answer` is what the call in flight is doing or said. `last` is the
 * last thing ctower actually answered, held across a re-ask so the page keeps
 * its shape while one is out. Without that, recording anything here destroyed
 * its own receipt: a send re-reads, the re-read went to "asking", the pane the
 * receipt lived in unmounted, and the operator was told nothing about a write
 * that had already happened.
 *
 * `last` is dropped the moment the question changes — another thread, another
 * filter — because holding it there would be showing one answer under another
 * question, which is the dishonest half of this pattern.
 */
export interface Held<T> {
  readonly answer: Answer<T>;
  readonly last: T | null;
}

export function useThreads(unreadOnly: boolean, reloadKey: number): Held<InboxThreadList> {
  return useHeld(
    () => ask(() => reads.listInboxThreads({ unread: unreadOnly })),
    unreadOnly ? "unread" : "all",
    [unreadOnly, reloadKey]
  );
}

/**
 * Who this console may write to. Asked once per reload rather than per compose,
 * because it is also where a reply's project key comes from and a thread cannot
 * be answered before it is known.
 */
export function useCorrespondents(reloadKey: number): Held<InboxCorrespondentList> {
  return useHeld(() => ask(() => reads.listInboxCorrespondents({})), "all", [reloadKey]);
}

/**
 * The open thread. With none open there is no question to ask, so this stays on
 * the working state and the page draws the compose pane instead — nothing here
 * ever renders as a thread that was not read.
 */
export function useThread(threadId: string | null, reloadKey: number): Held<InboxThread> {
  return useHeld(
    () =>
      threadId === null
        ? Promise.resolve(ASKING as Answer<InboxThread>)
        : ask(() => reads.readInboxThread({ threadId })),
    threadId ?? "",
    [threadId, reloadKey]
  );
}

function useHeld<T>(
  run: () => Promise<Answer<T>>,
  identity: string,
  deps: DependencyList
): Held<T> {
  const [answer, setAnswer] = useState<Answer<T>>(ASKING);
  const [held, setHeld] = useState<{ readonly identity: string; readonly value: T } | null>(null);
  // The call is rebuilt every render and the effect is keyed by what actually
  // changes the question, so the closure is read through a ref rather than
  // becoming a dependency that re-asks on every keystroke elsewhere.
  const latest = useRef(run);
  latest.current = run;

  useEffect((): (() => void) => {
    let live = true;
    setAnswer(ASKING);
    const load = async (): Promise<void> => {
      const next = await latest.current();
      if (!live) {
        return;
      }
      setAnswer(next);
      if (next.kind === "answered") {
        setHeld({ identity, value: next.value });
      }
    };
    void load();
    return (): void => {
      live = false;
    };
  }, deps);

  return { answer, last: held !== null && held.identity === identity ? held.value : null };
}
