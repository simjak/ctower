import type { CompanyBundleDocument } from "@ctower/client";
import { agentsIn } from "../agents/read";
import { projectsIn } from "../projects/read";

/**
 * Who works for this company, under the project they work in.
 *
 * A crew is a seat: the company bundle binds an agent profile to the subject
 * `<project key>:<seat>`, and that `<project key>` is literally the identifier
 * every project-addressed read takes. So a crew's own facts are the agent's —
 * the persona's name and the harness the profile pairs it with — and the group
 * it belongs to is the project the record already names.
 *
 * Everything a fleet dashboard wants beside that — is it working, on which
 * model, how many tokens, when it last moved — lives on a recorded session, and
 * a session names its crew with a string the caller authored. `SPEC.md` is
 * explicit that a seat key is never inferred from a subject or display text, so
 * this console cannot say the session called `qa-crew-4` is the crew the bundle
 * calls QA. Those facts are therefore absent from a crew here rather than
 * approximated, and the screen draws an absence where it has one.
 *
 * One reader, over readers. The persona and harness resolution is
 * `agents/read.ts`'s and the project's own name is `projects/read.ts`'s: a
 * second copy of either is how the Agents page and this one start disagreeing
 * about who works here. The order is the record's — the export is normalized
 * and deterministic (`SPEC.md`, § CompanyBundle) — so projects appear where the
 * company's record puts them and each project's crews follow the order the
 * record names their agents in.
 */
export interface Crew {
  /** The bundle's own subject, `<project key>:<seat>`. It travels; it does not render. */
  readonly subject: string;
  /** The name a person recognises, from the persona the profile names. */
  readonly name: string;
  /** What a person calls the harness, when this console can name it. */
  readonly harness: string | null;
}

export interface ProjectCrews {
  /** The key that addresses this project's reads. It travels; it does not render. */
  readonly key: string;
  readonly name: string;
  readonly crews: readonly Crew[];
}

export function rosterOf(document: CompanyBundleDocument): readonly ProjectCrews[] {
  const projects = projectsIn(document);
  const seats = new Map<string, Crew[]>(projects.map((project) => [project.key, []]));
  for (const agent of agentsIn(document)) {
    for (const subject of agent.seats) {
      // A subject whose namespace is not a project this company records is not
      // a crew and does not render as one: `principal:commander` is a
      // principal, and a seat in a project the bundle no longer carries has no
      // project to be drawn under.
      const held = seats.get(subject.slice(0, Math.max(subject.indexOf(":"), 0)));
      held?.push({ subject, name: agent.name, harness: agent.harness });
    }
  }
  return projects.map((project) => ({
    key: project.key,
    name: project.name,
    crews: seats.get(project.key) ?? [],
  }));
}

/** How many people this company records, across every project it records. */
export function crewCount(projects: readonly ProjectCrews[]): number {
  return projects.reduce((total, project) => total + project.crews.length, 0);
}
