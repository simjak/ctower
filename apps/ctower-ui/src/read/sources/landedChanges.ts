import { boundedProcess } from "../bounded";
import { projectSources } from "./mergeHistory";
import { noneOf, unreadOf, valueOf } from "./maybe";
import type { Known } from "./maybe";
import { redacted } from "./redact";
import type { ChangeReference } from "./signatures";
import type { DeliveredChange } from "../interface";

/**
 * Whether a project's trunk carries a change a crew's own records claim.
 *
 * A crew names its changes itself, in its status files and its crew-log lines.
 * That is a claim, not a delivery — so each reference is joined to the project's
 * first-parent trunk history, which is the same count the metrics screen uses
 * and which both of this fleet's workflows produce exactly one entry in: a merge
 * commit and a squash both leave one first-parent subject carrying `(#215)`.
 *
 * The three verdicts are kept apart on purpose. A change the trunk carries is
 * `landed`. A change it does not is `not-on-trunk` — true of a stacked branch's
 * PR, which is a real state and not a failure. A trunk that was not read at all
 * is `unchecked`, and says so, because "the trunk does not carry it" and "no
 * trunk was read" are opposite claims about the same change.
 *
 * No network and no forge. This surface has no credential for GitHub and would
 * have to invent a host to build a link, so it renders the reference the crew
 * wrote and the trunk fact it can check, and nothing else.
 */

const WINDOW_DAYS = 400;
const UNIT = "\u001f";
const SUBJECT_CAP = 120;

/** How a first-parent subject names the change it landed. */
const LANDED_AS = /\(#(\d{1,6})\)/u;

interface TrunkEntry {
  readonly day: string;
  readonly subject: string;
}

/** The repository a crew-log `project` names, when this surface measures one. */
function rootFor(project: string): string | null {
  const sources = projectSources();
  const matched =
    sources.find((source) => source.key === project) ??
    sources.find((source) => source.label === project);
  return matched?.root ?? null;
}

async function trunkOf(root: string): Promise<string> {
  try {
    return (await boundedProcess({ op: "git.trunkRef", root })).trim();
  } catch {
    return "origin/main";
  }
}

/** Every change the trunk landed in the window, keyed by its reference. */
async function landedIn(root: string): Promise<ReadonlyMap<string, TrunkEntry>> {
  const trunk = await trunkOf(root);
  const log = await boundedProcess({
    op: "git.trunkLog",
    root,
    ref: trunk,
    days: WINDOW_DAYS,
  });
  const landed = new Map<string, TrunkEntry>();
  for (const line of log.split("\n")) {
    const [at, subject] = line.split(UNIT);
    if (at === undefined || subject === undefined) {
      continue;
    }
    const matched = LANDED_AS.exec(subject);
    if (matched === null) {
      continue;
    }
    const reference = `#${matched[1] ?? ""}`;
    if (!landed.has(reference)) {
      landed.set(reference, { day: at.slice(0, 10), subject });
    }
  }
  return landed;
}

function unchecked(entry: ChangeReference, detail: Known<string>): DeliveredChange {
  return {
    reference: entry.reference,
    citedIn: redacted(entry.citedIn),
    project: entry.project,
    projectFromCrew: entry.projectFromCrew,
    verdict: "unchecked",
    verdictLabel: "no trunk read",
    detail,
  };
}

/** One trunk read per project, so a crew that moved is joined against both. */
type Trunks = ReadonlyMap<string, Known<ReadonlyMap<string, TrunkEntry>>>;

async function trunksFor(references: readonly ChangeReference[]): Promise<Trunks> {
  const projects = [
    ...new Set(
      references.flatMap((entry) => (entry.project.known === "value" ? [entry.project.value] : []))
    ),
  ];
  const read = await Promise.all(
    projects.map(
      async (project): Promise<readonly [string, Known<ReadonlyMap<string, TrunkEntry>>]> => {
        const root = rootFor(project);
        if (root === null) {
          return [
            project,
            noneOf(`this surface reads no repository for the project ${project}`),
          ] as const;
        }
        try {
          return [project, valueOf(await landedIn(root))] as const;
        } catch (error: unknown) {
          return [
            project,
            unreadOf<ReadonlyMap<string, TrunkEntry>>(
              error instanceof Error ? error.message : "the trunk history could not be read"
            ),
          ] as const;
        }
      }
    )
  );
  return new Map(read);
}

export interface LandedJoin {
  readonly changes: readonly DeliveredChange[];
  /** What was joined against, stated so the verdicts can be re-derived by hand. */
  readonly note: string;
}

/**
 * De-duplicate on the pair, not the number. Two projects can each hold a `#1`,
 * and collapsing them would put one repository's subject under the other's
 * reference.
 */
function keyOf(entry: ChangeReference): string {
  return `${entry.project.known === "value" ? entry.project.value : entry.project.known}|${entry.reference}`;
}

export async function readLandedChanges(
  references: readonly ChangeReference[],
  nowMs: number
): Promise<LandedJoin> {
  const unique = [...new Map(references.map((entry) => [keyOf(entry), entry])).values()];
  if (unique.length === 0) {
    return { changes: [], note: "no record this crew wrote names a change reference" };
  }

  const trunks = await trunksFor(unique);
  const window = new Date(nowMs - WINDOW_DAYS * 86_400_000).toISOString().slice(0, 10);
  const projects = [...trunks.keys()].sort((left, right) => left.localeCompare(right));
  return {
    changes: unique.map((entry): DeliveredChange => {
      if (entry.project.known !== "value") {
        return unchecked(
          entry,
          entry.project.known === "none"
            ? noneOf(
                "the record that named this change is filed under no project, so no trunk is its own"
              )
            : unreadOf(entry.project.reason)
        );
      }
      const trunk = trunks.get(entry.project.value);
      if (trunk?.known !== "value") {
        return unchecked(
          entry,
          trunk ?? noneOf(`no trunk was read for the project ${entry.project.value}`)
        );
      }
      const hit = trunk.value.get(entry.reference);
      if (hit === undefined) {
        return {
          reference: entry.reference,
          citedIn: redacted(entry.citedIn),
          project: entry.project,
          projectFromCrew: entry.projectFromCrew,
          verdict: "not-on-trunk",
          verdictLabel: "not on trunk",
          detail: noneOf(
            `no first-parent entry on ${entry.project.value}'s trunk since ${window} names ${entry.reference} — a stacked branch's change is a real state, not a failed read`
          ),
        };
      }
      const subject =
        hit.subject.length > SUBJECT_CAP ? `${hit.subject.slice(0, SUBJECT_CAP)}…` : hit.subject;
      return {
        reference: entry.reference,
        citedIn: redacted(entry.citedIn),
        project: entry.project,
        projectFromCrew: entry.projectFromCrew,
        verdict: "landed",
        verdictLabel: `landed ${hit.day}`,
        detail: valueOf(redacted(subject)),
      };
    }),
    note:
      projects.length === 0
        ? "the references below are what this crew claimed; none of them is filed under a project, so no trunk could check them"
        : `verdicts joined against the first-parent trunk history of ${projects.join(" and ")} since ${window}, each reference against the trunk of the project its own record was filed under; a reference is what the crew wrote, a verdict is what the trunk carries`,
  };
}
