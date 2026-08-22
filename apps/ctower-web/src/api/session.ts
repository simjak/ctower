/**
 * Admission to the development server, which is not authority at the API.
 *
 * The server that serves this app holds the operator credential and attaches it
 * to everything it proxies, so reaching that server is reaching operator
 * authority. Bound to loopback that is only the operator; bound to the tailnet
 * so the wizard can be walked from a laptop, it is every host on the tailnet.
 *
 * So the server prints a token at startup and admits nobody without it. This
 * module is where the browser holds that token. Three properties matter:
 *
 * - It is not the API bearer. The server strips it before forwarding anything,
 *   the API never sees it, and holding it grants nothing at the API.
 * - It lives in `sessionStorage`, so it dies with the tab rather than lingering
 *   on the disk of a shared machine.
 * - Nothing here crosses a boundary. The token is proved by `probeAdmission` in
 *   the bounded chokepoint, which is the only module in this app that may.
 */

export const SESSION_HEADER = "x-ctower-web-session";
/** Set by the server on its own refusal, so it is never read as the API's. */
export const GATE_HEADER = "x-ctower-web-gate";
export const ADMISSION_PATH = "/__ctower-web-session";
export const SESSION_REFUSED_EVENT = "ctower:session-refused";

const SLOT = "ctower-web.session";

let held: string | null = readSlot();

export function sessionToken(): string | null {
  return held;
}

/** Called only after the server has admitted this exact token. */
export function keepSession(token: string): void {
  held = token;
  writeSlot(token);
}

/**
 * The server no longer admits what this browser holds — it was restarted, and
 * a restart mints a new token. Forget it and say so, once.
 */
export function forgetSession(): void {
  if (held === null) {
    return;
  }
  held = null;
  writeSlot(null);
  window.dispatchEvent(new CustomEvent(SESSION_REFUSED_EVENT));
}

/** Storage may be blocked; admission then lasts exactly as long as the page. */
function readSlot(): string | null {
  try {
    return window.sessionStorage.getItem(SLOT);
  } catch {
    return null;
  }
}

function writeSlot(value: string | null): void {
  try {
    if (value === null) {
      window.sessionStorage.removeItem(SLOT);
      return;
    }
    window.sessionStorage.setItem(SLOT, value);
  } catch {
    /* held in memory for this page; the operator pastes again after a reload */
  }
}
