import { boundedProcess } from "../bounded";
import { asRecord } from "../json";
import { healthOf, registryOf } from "./cadenceHealth";
import { redacted } from "./redact";
import type { Beat, CadenceRegistry } from "../interface";

/**
 * The second real cadence source: this account's systemd user timers.
 *
 * It exists to prove the swap seam. Heartbeats renders whichever source
 * `CTOWER_UI_CADENCE_SOURCE` selects, and neither source is a fixture — both
 * are live scheduled wakes on this host, so exercising the seam never puts an
 * invented row on the screen.
 */

function microsecondsToIso(value: unknown): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return null;
  }
  const milliseconds = Math.round(value / 1000);
  const at = new Date(milliseconds);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
}

function microseconds(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.round(value / 1000)
    : null;
}

function seatOf(unit: string): string {
  const stem = unit.replace(/\.timer$/u, "");
  const [head] = stem.split("-");
  return head ?? stem;
}

export async function readSystemdCadence(): Promise<CadenceRegistry> {
  const now = Date.now();
  const text = await boundedProcess({
    command: "systemctl",
    args: ["--user", "list-timers", "--all", "--output=json"],
  });
  const parsed: unknown = JSON.parse(text);
  const rows = Array.isArray(parsed) ? parsed : [];
  const beats: Beat[] = rows.map((row): Beat => {
    const timer = asRecord(row, "systemd.timer");
    const unit = typeof timer.unit === "string" ? timer.unit : "unnamed.timer";
    const lastMs = microseconds(timer.last);
    const nextMs = microseconds(timer.next);
    // A timer states its own next fire, so the interval it implies is the gap
    // between the two recorded stamps; nothing is assumed about its calendar.
    const interval = lastMs !== null && nextMs !== null && nextMs > lastMs ? nextMs - lastMs : null;
    const { health, why } = healthOf(lastMs, interval, now);
    return {
      seat: redacted(seatOf(unit)),
      beat: redacted(unit),
      schedule:
        interval === null ? "systemd timer" : `every ${Math.round(interval / 60_000).toString()}m`,
      lastFire: microsecondsToIso(timer.last),
      nextFire: microsecondsToIso(timer.next),
      health,
      why,
    };
  });
  return registryOf(beats, "systemctl --user list-timers", new Date(now).toISOString());
}
