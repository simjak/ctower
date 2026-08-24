import type { Crew } from "./crew";
import type { ProjectFleet } from "./ProjectGroup";

/**
 * The company the bench draws with.
 *
 * Fixtures, and they say so: this is a bench, no read runs here, and nobody on
 * this screen is a person in the record. They exist to put every state a row can
 * be in on one screen at one time — including the states a live tower will not
 * produce on demand, such as a run that failed and a project whose read refused.
 *
 * The three projects are the three the operator's own walk found rendered as
 * monospace keys (`ctower`, `manibo`, `bh-loop`). Here they carry the name the
 * project component gives itself, which is the whole point of the fix.
 */
const TOWER = "Control Tower";
const MANIBO = "Manibo";
const LOOP = "BH Loop";

/** The staff, as the bundle records them: a name, a job, and a harness. */
const RECORDED: readonly (readonly [string, Crew])[] = [
  [TOWER, named("Ada", "Chief of staff · CEO", "Claude Code")],
  [TOWER, named("Luna", "Engineer · Gate integrity", "Claude Code")],
  [TOWER, named("Ox", "Reviewer · Quality", "Codex")],
  [TOWER, named("Vela", "Engineer · Second seat, nights", "Claude Code")],
  [MANIBO, named("Sol", "Researcher · Long reads", "Hermes")],
  [MANIBO, named("Juno", "Engineer · Delivery", "Codex")],
  [LOOP, named("Rhea", "Chief of staff · Operations", "Claude Code")],
  [LOOP, named("Kepler", null, null)],
];

/**
 * Picture one: what a live tower answers today.
 *
 * Every crew's name, job and harness is read off the bundle and is real. Not one
 * row carries a state, a model, a spend or a time, because a session names its
 * crew with a caller-authored string and the contract has no key that joins one
 * to a bundle subject. The header line beside each project IS real — sessions
 * answer per project, and a project key is the one thing both sides share.
 */
export const TODAY: readonly ProjectFleet[] = [
  {
    name: TOWER,
    crews: crewsOf(TOWER),
    work: { kind: "answered", working: 2, gated: 1, tokens: 1_740_000 },
  },
  {
    name: MANIBO,
    crews: crewsOf(MANIBO),
    work: { kind: "answered", working: 0, gated: 0, tokens: 0 },
  },
  { name: LOOP, crews: crewsOf(LOOP), work: { kind: "refused" } },
];

/**
 * Picture two: the same eight crews once a run can name the crew it ran as.
 *
 * Nothing about the layout changes — the columns were always there and were
 * always empty. This is the design being asked for, and the difference between
 * the two pictures is exactly the size of the contract gap.
 */
export const ATTRIBUTED: readonly ProjectFleet[] = [
  {
    name: TOWER,
    crews: [
      run("Ada", "claude-fable-5", "working", 412_000, "2026-08-24T09:12:00Z"),
      run("Luna", "claude-opus-5", "delivered", 88_400, "2026-08-24T07:40:00Z"),
      run("Ox", "gpt-5.2-codex", "gated", 1_240_000, "2026-08-23T22:05:00Z"),
      run("Vela", "claude-opus-5", "working", 61_200, "2026-08-24T09:31:00Z"),
    ],
    work: { kind: "answered", working: 2, gated: 1, tokens: 1_740_000 },
  },
  {
    name: MANIBO,
    crews: [
      run("Sol", "claude-sonnet-5", "failed", 9_800, "2026-08-23T18:31:00Z"),
      run("Juno", "gpt-5.2-codex", "blocked", 204_000, "2026-08-23T16:02:00Z"),
    ],
    work: { kind: "answered", working: 0, gated: 0, tokens: 214_000 },
  },
  {
    name: LOOP,
    crews: [
      run("Rhea", "claude-fable-5", "abandoned", 33_100, "2026-08-22T11:14:00Z"),
      crewsOf(LOOP)[1] ?? named("Kepler", null, null),
    ],
    work: { kind: "asking" },
  },
];

/** A company that has recorded nothing yet — the first thing a new tenant sees. */
export const NOBODY: readonly ProjectFleet[] = [];

/** A project on the books with nobody on it, beside one that is fully staffed. */
export const UNSTAFFED: readonly ProjectFleet[] = [
  {
    name: MANIBO,
    crews: crewsOf(MANIBO),
    work: { kind: "answered", working: 1, gated: 0, tokens: 76_500 },
  },
  { name: LOOP, crews: [], work: { kind: "answered", working: 0, gated: 0, tokens: 0 } },
];

function crewsOf(project: string): readonly Crew[] {
  return RECORDED.filter(([where]) => where === project).map(([, crew]) => crew);
}

function named(name: string, role: string | null, harness: string | null): Crew {
  return { name, role, harness, model: null, standing: "unseen", tokens: null, lastActive: null };
}

function run(
  name: string,
  model: string,
  standing: Crew["standing"],
  tokens: number,
  lastActive: string
): Crew {
  const recorded = RECORDED.find(([, crew]) => crew.name === name)?.[1];
  return { ...(recorded ?? named(name, null, null)), model, standing, tokens, lastActive };
}
