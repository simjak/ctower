import { readFile } from "node:fs/promises";
import { asRecord, asString } from "../json";
import { redacted } from "./redact";

/**
 * Principal-ULID to seat-name resolution, app-wide.
 *
 * The design audit's first finding was that the product's core concept — *who*
 * is doing the work — is invisible: board cards showed a custodian truncated to
 * one character, and the ticket header showed a raw 36-character ULID where a
 * name belongs.
 *
 * ctower does not record a display name for a principal, and round-3 QA (#241)
 * found this citing AC-TM-07 for it — a criterion about the *tenant's* display
 * identity, which is a different subject. `read/futureSources.ts` now carries
 * the honest statement: nothing is filed for this yet.
 *
 * So this is the seam rather than a guess: it resolves from an operator-
 * maintained map when one is configured, and otherwise resolves nothing — and
 * every screen renders `seat unnamed` with the full principal in the title,
 * instead of a ULID chopped to noise. When the record carries display facts,
 * this module reads them and no screen changes.
 */

let cached: Readonly<Record<string, string>> | null = null;

async function loadMap(): Promise<Readonly<Record<string, string>>> {
  const path = process.env.CTOWER_UI_SEAT_MAP;
  if (path === undefined || path === "") {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(await readFile(path, "utf8"));
    const rows = asRecord(parsed, "seat map");
    return Object.fromEntries(
      Object.entries(rows).map(([principal, name]) => [
        principal,
        redacted(asString(name, `seat map ${principal}`)),
      ])
    );
  } catch {
    // an unreadable map resolves nothing; it never invents a name
    return {};
  }
}

export async function seatNames(): Promise<Readonly<Record<string, string>>> {
  cached ??= await loadMap();
  return cached;
}

/** The seat's name, or `null` when the record carries none for this principal. */
export function seatNameOf(
  map: Readonly<Record<string, string>>,
  principalId: string
): string | null {
  return map[principalId] ?? null;
}

/** What would make these names resolve, for the screens that say so. */
export { NO_SEAT_NAME as SEAT_NAME_SOURCE } from "../futureSources";
