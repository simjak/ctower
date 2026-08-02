import { boundedProcess } from "../bounded";
import { redacted } from "./redact";
import type { Candidate } from "../selectors";
import type { DeliveryMeasure, MergeDay, ProjectMerges, Reading } from "../interface";

/**
 * Interim source: merged changes per day, read from each project's git history.
 *
 * The count is `git log --first-parent <default branch>`: one entry per change
 * that landed on the trunk. That is the honest count for both workflows in this
 * fleet — a merge commit and a squash both produce exactly one first-parent
 * entry — and it is stated on the screen rather than left to be assumed.
 *
 * Change failure rate is measured the only way the record supports: entries
 * whose subject begins `Revert`. The screen says so, because that measures what
 * was reverted on the trunk, not what broke in an environment nobody records.
 *
 * Every other DORA measure needs a deploy event, an incident pair or a hotfix
 * label that no project keeps. Those are not computed here at all — the screen
 * declares them, and this module refuses to invent the half it cannot read.
 */

const WINDOW_DAYS = 7;
const UNIT = "\u001f";

export interface ProjectSource {
  readonly key: string;
  readonly label: string;
  readonly root: string;
}

function environment(name: string, fallback: string): string {
  const value = process.env[name];
  return value === undefined || value === "" ? fallback : value;
}

/** The projects this surface measures. Overridable, so a copy can be measured. */
export function projectSources(): readonly ProjectSource[] {
  return [
    {
      key: "ctower",
      label: "ctower",
      root: environment("CTOWER_UI_PROJECT_CTOWER", "/srv/projects/ctower"),
    },
    {
      key: "manibo",
      label: "lastmachines",
      root: environment("CTOWER_UI_PROJECT_MANIBO", "/srv/projects/manibo"),
    },
    {
      key: "bhloop",
      label: "bh-loop",
      root: environment("CTOWER_UI_PROJECT_BHLOOP", "/srv/projects/bh-loop"),
    },
  ];
}

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

/** The last `WINDOW_DAYS` day keys, oldest first, ending today in UTC. */
export function windowDays(now: number): readonly string[] {
  return Array.from({ length: WINDOW_DAYS }, (_, index) =>
    new Date(now - (WINDOW_DAYS - 1 - index) * 86_400_000).toISOString().slice(0, 10)
  );
}

async function trunkOf(root: string): Promise<string> {
  try {
    const head = await boundedProcess({
      command: "git",
      args: ["-C", root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
    });
    return head.trim();
  } catch {
    // a checkout with no remote HEAD still has a trunk; name it explicitly
    return "origin/main";
  }
}

async function readProject(source: ProjectSource, now: number): Promise<ProjectMerges> {
  const trunk = await trunkOf(source.root);
  const log = await boundedProcess({
    command: "git",
    args: [
      "-C",
      source.root,
      "log",
      "--first-parent",
      trunk,
      `--since=${WINDOW_DAYS.toString()} days ago`,
      "--format=%aI%x1f%s",
    ],
    maxBytes: 2_000_000,
  });
  const entries = log
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .flatMap((line) => {
      const [at, subject] = line.split(UNIT);
      return at === undefined || subject === undefined ? [] : [{ at, subject }];
    });

  const byDay = new Map<string, number>();
  for (const day of windowDays(now)) {
    byDay.set(day, 0);
  }
  let landed = 0;
  for (const entry of entries) {
    const key = dayKey(entry.at);
    const current = byDay.get(key);
    if (current !== undefined) {
      byDay.set(key, current + 1);
      landed += 1;
    }
  }
  const reverted = entries.filter((entry) => /^revert/iu.test(entry.subject)).length;
  return {
    key: source.key,
    label: redacted(source.label),
    trunk: redacted(trunk),
    days: [...byDay.entries()].map(([day, count]): MergeDay => ({ day, count })),
    landed,
    reverted,
  };
}

/** One candidate per project, so a project that cannot be read stays visible. */
export async function mergeCandidates(now: number): Promise<readonly Candidate<ProjectMerges>[]> {
  return await Promise.all(
    projectSources().map(async (source): Promise<Candidate<ProjectMerges>> => {
      try {
        return {
          reading: { state: "present", value: await readProject(source, now) },
          orderBy: source.key,
        };
      } catch (error: unknown) {
        return {
          reading: {
            state: "unavailable",
            failure: {
              reason: `${source.label}: ${error instanceof Error ? error.message : "unreadable"}`,
              failureClass: "permanent",
              attempts: 1,
              elapsedMs: 0,
            },
          },
          orderBy: source.key,
        };
      }
    })
  );
}

/** Change failure rate, the only DORA measure this record can support. */
export function changeFailureRate(projects: readonly ProjectMerges[]): DeliveryMeasure {
  const landed = projects.reduce((total, project) => total + project.landed, 0);
  const reverted = projects.reduce((total, project) => total + project.reverted, 0);
  if (landed === 0) {
    return {
      title: "Change failure rate",
      value: null,
      unit: null,
      target: "target ≤ 15%",
      note: "no change landed on a trunk in the window, so there is no rate to state.",
      source: "src: first-parent trunk history · reverts by subject",
    };
  }
  return {
    title: "Change failure rate",
    value: ((reverted / landed) * 100).toFixed(1),
    unit: "%",
    target: "target ≤ 15%",
    note: `${reverted.toString()} of ${landed.toString()} trunk changes were reverts. This measures what was reverted on the trunk — not what broke in an environment, which no project records.`,
    source: "src: first-parent trunk history · reverts by subject",
  };
}

export type MergeReading = Reading<readonly ProjectMerges[]>;
