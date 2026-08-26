import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import { UserPlus } from "lucide-react";
import type { CompanyBundleDocument } from "@ctower/client";
import { Button, Card, PageHead } from "../ui/primitives";
import { NewCrew } from "./NewCrew";
import { ProjectGroup } from "./ProjectGroup";
import { crewCount, rosterOf } from "./roster";
import { sessionsOfProject, useSessions } from "./useSessions";

/**
 * The Crews screen: who works for this company, by the project they work in.
 *
 * The screen this replaces was a three-pane cockpit whose two live panes could
 * not be filled — a rail of monospace project keys, no seats in any of them,
 * and an empty state pointing at a page that could not make one either. This is
 * a list, because a list is what a roster is, and because every column in it is
 * either a fact the record already answers or an absence drawn as one.
 *
 * Two reads and no third. The company bundle says who works here, under the
 * name each project gave itself; `listProjectSessions` says what each project
 * has running. Nothing joins them at a row: a session names its crew with a
 * caller-authored string, and `SPEC.md` forbids inferring a seat key from a
 * subject or display text. So the project header carries the work and the rows
 * carry the people, which is exactly as far as the record goes.
 *
 * **This screen issues no write.** Making a crew ends in a ceremony the
 * operator completes with material only he holds, and no operation reads a seat
 * back to confirm it — so the way in says that in words rather than drawing a
 * form that could take an answer and never report on it.
 */
export function CrewsPage({
  document,
}: {
  readonly document: CompanyBundleDocument;
}): ReactElement {
  const projects = useMemo(() => rosterOf(document), [document]);
  const sessions = useSessions(useMemo(() => projects.map((project) => project.key), [projects]));
  // Making a crew is a moment, not a place: it opens over the roster and is
  // gone when it closes, so it stays out of the address the way every other
  // pop-up in this console does.
  const [making, setMaking] = useState(false);

  return (
    <>
      <PageHead title="Crews" subtitle={across(projects.length, crewCount(projects)) ?? undefined}>
        <Button
          variant="primary"
          onClick={(): void => {
            setMaking(true);
          }}
        >
          <UserPlus /> New crew
        </Button>
      </PageHead>
      {projects.length === 0 ? (
        <Card className="grid place-content-center px-6 py-12 text-center">
          <p className="m-0 text-sm text-muted">This company records no crew yet.</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {projects.map((project) => (
            <ProjectGroup
              key={project.key}
              project={project}
              sessions={sessionsOfProject(sessions.get(project.key))}
            />
          ))}
        </div>
      )}
      <NewCrew company={document.company.display_name} open={making} onOpenChange={setMaking} />
    </>
  );
}

/**
 * How many, and where — or nothing at all.
 *
 * A company with nobody on its books gets no count. "0 crews across 3 projects"
 * is a true sentence that reads as a broken one, and the projects below say the
 * same thing one at a time in words a person would use.
 */
function across(projects: number, crews: number): string | null {
  if (crews === 0) {
    return null;
  }
  const who = crews === 1 ? "1 crew" : `${String(crews)} crews`;
  return projects === 1 ? `${who} in 1 project` : `${who} across ${String(projects)} projects`;
}
