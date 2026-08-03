/**
 * Time rendering derived only from recorded timestamps.
 *
 * Nothing here invents a clock fact: every value is a difference between two
 * timestamps the record actually carries, or that timestamp itself in UTC —
 * the zone the record is written in, so no local-zone conversion is implied.
 */

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

function pad(value: number): string {
  return value.toString().padStart(2, "0");
}

export function spanText(milliseconds: number): string {
  const span = Math.max(0, milliseconds);
  if (span >= DAY) {
    return `${Math.floor(span / DAY).toString()}d ${pad(Math.floor((span % DAY) / HOUR))}h`;
  }
  if (span >= HOUR) {
    return `${Math.floor(span / HOUR).toString()}h ${pad(Math.floor((span % HOUR) / MINUTE))}m`;
  }
  if (span >= MINUTE) {
    return `${Math.floor(span / MINUTE).toString()}m`;
  }
  return `${Math.floor(span / 1000).toString()}s`;
}

export function elapsedSince(isoTimestamp: string, now: number): string | null {
  const started = Date.parse(isoTimestamp);
  if (Number.isNaN(started)) {
    return null;
  }
  return spanText(now - started);
}

export function spanBetween(fromIso: string, toIso: string): string | null {
  const from = Date.parse(fromIso);
  const to = Date.parse(toIso);
  if (Number.isNaN(from) || Number.isNaN(to)) {
    return null;
  }
  return spanText(to - from);
}

export function clockText(isoTimestamp: string): string {
  const at = new Date(isoTimestamp);
  if (Number.isNaN(at.getTime())) {
    return isoTimestamp;
  }
  return `${pad(at.getUTCHours())}:${pad(at.getUTCMinutes())}:${pad(at.getUTCSeconds())}`;
}

export function dayText(isoTimestamp: string): string {
  const at = new Date(isoTimestamp);
  if (Number.isNaN(at.getTime())) {
    return isoTimestamp;
  }
  return `${at.getUTCFullYear().toString()}-${pad(at.getUTCMonth() + 1)}-${pad(at.getUTCDate())}`;
}

export function stampText(isoTimestamp: string): string {
  return `${dayText(isoTimestamp)} ${clockText(isoTimestamp)} UTC`;
}

export function shortId(identifier: string): string {
  return identifier.length > 8 ? `${identifier.slice(0, 8)}…` : identifier;
}
