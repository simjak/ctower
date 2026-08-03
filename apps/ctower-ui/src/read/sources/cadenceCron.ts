import { stat } from "node:fs/promises";
import { basename } from "node:path";
import { boundedProcess } from "../bounded";
import { healthOf, HEALTH_RULE, registryOf } from "./cadenceHealth";
import { noneOf, unreadOf, valueOf } from "./maybe";
import type { Known } from "./maybe";
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

/**
 * Beats whose fire marker is not one of the three conventional names.
 *
 * Round-3 QA (#238) found `ctower-feed-notify` rendered as never-fired while it
 * was firing every ten minutes: it writes `state/ctower-feed-cursor.json` on
 * every run — reached, quiet or not-reached alike — and sends its stdout to
 * `/dev/null`, so none of the three guessed filenames could ever exist. A row
 * that can go neither green nor red carries no signal at all, which is the
 * "a check that reports clean because it didn't look" failure in its quiet form.
 *
 * A beat is registered here by the file it actually touches, so the guess is a
 * fallback rather than the whole rule. A beat in neither the table nor the
 * convention is named as a registry gap on the surface, not shrugged at.
 */
const REGISTERED_MARKERS: Readonly<Record<string, string>> = {
  "ctower-feed-notify": "state/ctower-feed-cursor.json",
};

/** Every path this source will accept as `<name>` having fired, best first. */
export function markerCandidates(name: string): readonly string[] {
  const root = missionControlRoot();
  const registered = REGISTERED_MARKERS[name];
  return [
    ...(registered === undefined ? [] : [`${root}/${registered}`]),
    `${root}/state/logs/${name}.log`,
    `${root}/state/.${name}.last`,
    `${root}/state/.${name}.heartbeat`,
  ];
}

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

/**
 * The last fire, or why it is unknown.
 *
 * A marker that does not exist means the beat has not fired since the markers
 * were introduced. A marker that exists and cannot be read means this surface
 * does not know — round-1 review found both collapsed into "no last fire",
 * which turns an I/O failure into a claim about the beat.
 */
async function lastFireAt(name: string): Promise<Known<number>> {
  for (const candidate of markerCandidates(name)) {
    try {
      return valueOf((await stat(candidate)).mtimeMs);
    } catch (error: unknown) {
      const code = (error as { readonly code?: unknown }).code;
      if (code === "ENOENT") {
        continue;
      }
      return unreadOf(
        `${candidate} exists but could not be read: ${error instanceof Error ? error.message : "unknown error"}`
      );
    }
  }
  // this is a statement about the registry, not about the beat: cron holds the
  // beat, and no file this source knows to look at records its fires
  return noneOf(
    `no fire marker exists for ${name} yet — cron registers it, and none of the ${markerCandidates(name).length.toString()} paths this source reads has ever been written, so its liveness cannot be established here`
  );
}

function beatName(command: string): string {
  return basename(command.split(/\s+/u)[0] ?? command);
}

export async function readCronCadence(): Promise<CadenceRegistry> {
  const now = Date.now();
  const text = await boundedProcess({ op: "crontab.list" });
  const owner = process.env.USER ?? "the crontab owner";
  const beats: Beat[] = await Promise.all(
    parseCrontab(text).map(async (entry): Promise<Beat> => {
      const name = beatName(entry.command);
      const last = await lastFireAt(name);
      const lastMs = last.known === "value" ? last.value : null;
      // an unread marker and a marker that was never written are different
      // claims, and each carries its own sentence rather than collapsing into
      // one generic "no last fire is recorded"
      const { health, why } =
        last.known === "value"
          ? healthOf(last.value, intervalMs(entry.schedule), now)
          : ({
              health: "unknown",
              why: last.known === "unread" ? last.reason : last.why,
            } as const);
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
    new Date(now).toISOString(),
    HEALTH_RULE
  );
}
