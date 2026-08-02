import { stat } from "node:fs/promises";
import { basename } from "node:path";
import { boundedProcess } from "../bounded";
import { healthOf, registryOf } from "./cadenceHealth";
import { missionControlRoot } from "./paths";
import { redacted } from "./redact";
import type { Beat, CadenceRegistry } from "../interface";

/**
 * Interim source: the host crontab, plus the marker files each beat touches.
 *
 * `crontab -l` is the registry — the schedule and the command are exactly what
 * cron holds. The last fire is a filesystem fact: the mtime of the beat's own
 * log or `.last` marker under Mission Control's `state/`. The next fire is
 * computed from the recorded schedule; it is a derivation from two real values,
 * and the screen says so.
 *
 * Nothing here writes a crontab or touches a marker.
 */

const MARKER_CANDIDATES = (name: string): readonly string[] => [
  `${missionControlRoot()}/state/logs/${name}.log`,
  `${missionControlRoot()}/state/.${name}.last`,
  `${missionControlRoot()}/state/.${name}.heartbeat`,
];

interface CronEntry {
  readonly schedule: string;
  readonly command: string;
}

function parseCrontab(text: string): readonly CronEntry[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("#") && !/^[A-Z_]+=/u.test(line))
    .flatMap((line) => {
      const parts = line.split(/\s+/u);
      if (parts.length < 6) {
        return [];
      }
      return [{ schedule: parts.slice(0, 5).join(" "), command: parts.slice(5).join(" ") }];
    });
}

/** Every minute-of-hour a star, step, literal or list minute field selects. */
function minuteField(field: string): readonly number[] {
  if (field === "*") {
    return Array.from({ length: 60 }, (_, index) => index);
  }
  const step = /^\*\/(\d+)$/u.exec(field);
  if (step !== null) {
    const every = Number(step[1]);
    return every > 0
      ? Array.from({ length: Math.ceil(60 / every) }, (_, index) => index * every)
      : [];
  }
  return field
    .split(",")
    .map((part) => Number(part))
    .filter((value) => Number.isInteger(value) && value >= 0 && value < 60);
}

/** The interval this schedule implies, when its minute field states one. */
function intervalMs(schedule: string): number | null {
  const minutes = minuteField(schedule.split(/\s+/u)[0] ?? "*");
  if (minutes.length < 2) {
    return schedule.split(/\s+/u)[1] === "*" ? 60 * 60_000 : null;
  }
  const gaps = minutes.slice(1).map((value, index) => value - (minutes[index] ?? 0));
  return Math.min(...gaps) * 60_000;
}

function nextFireAt(schedule: string, now: number): string | null {
  const minutes = minuteField(schedule.split(/\s+/u)[0] ?? "*");
  if (minutes.length === 0) {
    return null;
  }
  const at = new Date(now);
  at.setUTCSeconds(0, 0);
  for (let ahead = 1; ahead <= 60 * 25; ahead += 1) {
    const candidate = new Date(at.getTime() + ahead * 60_000);
    if (minutes.includes(candidate.getUTCMinutes())) {
      return candidate.toISOString();
    }
  }
  return null;
}

async function lastFireAt(name: string): Promise<number | null> {
  for (const candidate of MARKER_CANDIDATES(name)) {
    try {
      return (await stat(candidate)).mtimeMs;
    } catch {
      continue;
    }
  }
  return null;
}

function beatName(command: string): string {
  return basename(command.split(/\s+/u)[0] ?? command);
}

export async function readCronCadence(): Promise<CadenceRegistry> {
  const now = Date.now();
  const text = await boundedProcess({ command: "crontab", args: ["-l"] });
  const owner = process.env.USER ?? "the crontab owner";
  const beats: Beat[] = await Promise.all(
    parseCrontab(text).map(async (entry): Promise<Beat> => {
      const name = beatName(entry.command);
      const lastMs = await lastFireAt(name);
      const { health, why } = healthOf(lastMs, intervalMs(entry.schedule), now);
      return {
        seat: redacted(owner),
        beat: redacted(name),
        schedule: redacted(entry.schedule),
        lastFire: lastMs === null ? null : new Date(lastMs).toISOString(),
        nextFire: nextFireAt(entry.schedule, now),
        health,
        why,
      };
    })
  );
  return registryOf(
    beats,
    `crontab -l · fires from ${missionControlRoot()}/state`,
    new Date(now).toISOString()
  );
}
