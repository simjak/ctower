import { uuid } from "../../api/telemetry";

const STORE_PREFIX = "ctower-web.apply.";

/**
 * One command identity per plan, preserved across a reload.
 *
 * `AC-UX-09`: a browser command stays visibly unsent or pending until the
 * server accepts it, and a retry — including a retry after the operator
 * reloaded the page — carries the same key rather than becoming a second
 * command. The key is derived per plan digest, so changing the company produces
 * a different plan and therefore a different command, which is correct: it is a
 * different act.
 */
export function commandKeyFor(planDigest: string): string {
  const slot = `${STORE_PREFIX}${planDigest}`;
  try {
    const held = window.localStorage.getItem(slot);
    if (held !== null && held !== "") {
      return held;
    }
    const minted = uuid();
    window.localStorage.setItem(slot, minted);
    return minted;
  } catch {
    // A blocked storage partition costs the across-reload guarantee and nothing
    // else: the key is still stable for the life of this attempt.
    return uuid();
  }
}
