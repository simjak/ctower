import { uuid } from "../../api/telemetry";

const STORE_PREFIX = "ctower-web.apply.";

/**
 * One command identity per plan, for the life of the attempt chain.
 *
 * `AC-UX-09`: a browser command stays visibly unsent or pending until the
 * server accepts it, and a retry — including one after a reload — carries the
 * same key rather than becoming a second command. The key is derived per plan
 * digest, so changing the company produces a different plan and a different
 * command, which is correct: that is a different act.
 *
 * The in-memory map is not a nicety. Storage can be blocked, and the previous
 * version minted a fresh UUID on every call in that case — so a manual retry of
 * the same plan became a *different command*, which is exactly what O10's
 * same-key rule exists to prevent. Blocked storage now costs only the
 * across-reload guarantee, which is what this function always claimed.
 */
const minted = new Map<string, string>();

/** Whether this page can carry a command key across a reload. */
let durable = true;

export function commandKeyFor(planDigest: string): string {
  const held = minted.get(planDigest);
  if (held !== undefined) {
    return held;
  }
  const slot = `${STORE_PREFIX}${planDigest}`;
  try {
    const stored = window.localStorage.getItem(slot);
    if (stored !== null && stored !== "") {
      minted.set(planDigest, stored);
      return stored;
    }
  } catch {
    durable = false;
  }

  const key = uuid();
  minted.set(planDigest, key);
  try {
    window.localStorage.setItem(slot, key);
  } catch {
    durable = false;
  }
  return key;
}

/**
 * False when storage refused, so a screen can say that a retry survives this
 * page but not a reload rather than implying a guarantee it does not have.
 */
export function commandKeySurvivesReload(): boolean {
  return durable;
}
