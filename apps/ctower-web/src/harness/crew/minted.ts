import { useSyncExternalStore } from "react";
import type { Minted } from "./roster";

/**
 * The addresses this page load has minted, held above the panel that minted them.
 *
 * ctower serves no read for a seat, so the only addresses this screen can draw
 * are the receipts it was handed — and "handed" has to mean the session, not the
 * component. The crew panel is one tab among five on the harness page, and a tab
 * unmounts when the operator looks at another one. Held in the panel, an address
 * issued a moment ago would go back to `not read` on the way past Projects, and
 * the revoke control would go with it: the operator would be looking at a live
 * credential the screen had forgotten it minted.
 *
 * So the store outlives the panel and dies with the page, which is exactly the
 * claim the roster's own line makes. A reload still clears it, and that is not a
 * bug to fix here — it is the missing `listSeatCredentials` read, recorded as a
 * gap rather than papered over with storage that would outlive the truth.
 */
let held: readonly Minted[] = [];
const listeners = new Set<() => void>();

export function recordMinted(entry: Minted): void {
  held = [...held, entry];
  for (const listener of listeners) {
    listener();
  }
}

export function useMinted(): readonly Minted[] {
  return useSyncExternalStore(subscribe, snapshot);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return (): void => {
    listeners.delete(listener);
  };
}

function snapshot(): readonly Minted[] {
  return held;
}
