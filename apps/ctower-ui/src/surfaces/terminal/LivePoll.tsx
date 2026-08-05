"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import type { ReactElement } from "react";

/**
 * The poll this increment proposes: a client-side timer that asks the
 * existing server component to re-run, rather than a new fetch call site.
 *
 * Every screen here is `force-dynamic` and already re-reads its source on
 * each navigation; `router.refresh()` is that same re-render, replayed on an
 * interval instead of on a click. No new network-capable construct is
 * introduced by this file — it names no `fetch`, `EventSource` or child
 * process — so it adds nothing for the O10 chokepoint scan to classify.
 *
 * Renders nothing: it is mounted once per page for its side effect alone.
 */
export function LivePoll({ intervalMs = 5_000 }: { readonly intervalMs?: number }): ReactElement {
  const router = useRouter();
  useEffect((): (() => void) => {
    const timer = setInterval((): void => {
      router.refresh();
    }, intervalMs);
    return (): void => {
      clearInterval(timer);
    };
  }, [intervalMs, router]);
  return <></>;
}
