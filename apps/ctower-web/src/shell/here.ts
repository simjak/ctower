import { DESTINATIONS } from "./destinations";
import type { DestinationKey } from "./destinations";

/**
 * Where the operator is, kept in the address.
 *
 * A console whose location lives only in memory cannot be sent to anyone: the
 * board the operator is looking at, on the project it is reading, has to be one
 * link. The value is checked against the shell's own map rather than cast, so a
 * hand-edited address opens the default destination instead of a blank screen.
 */
const DEFAULT: DestinationKey = "company";

export function hereFromLocation(search: string): DestinationKey {
  const asked = new URLSearchParams(search).get("at");
  return DESTINATIONS.find((destination) => destination.key === asked)?.key ?? DEFAULT;
}

export function rememberHere(key: DestinationKey): void {
  const url = new URL(window.location.href);
  url.searchParams.set("at", key);
  window.history.replaceState(null, "", url);
}
