import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { PageHead } from "../ui/primitives";
import { Conversation } from "./Conversation";
import { CrewRail } from "./CrewRail";
import { crewCount, findCrew, firstCrew, rosterOf } from "./roster";
import { sessionsOfProject, useSessions } from "./useSessions";
import { Workspace } from "./Workspace";

/**
 * The cockpit: crews on the left, the conversation with one of them in the
 * middle, that crew's workspace on the right.
 *
 * The three panes are the reference console's, and exactly two of them carry a
 * real read: the roster is the active company bundle, and the work beside it is
 * that project's recorded sessions. The transcript, the composer, the steer
 * control and the terminal are drawn as absent, because the operations behind
 * them either have no implementation at this head or answer on a surface this
 * browser is not — and a pane that pretends is worse than a pane that says so.
 */
export function Cockpit({ document }: { readonly document: CompanyBundleDocument }): ReactElement {
  const projects = useMemo(() => rosterOf(document), [document]);
  const sessions = useSessions(useMemo(() => projects.map((p) => p.key), [projects]));
  const [picked, setPicked] = useState<string | null>(null);
  const crew = findCrew(projects, picked) ?? firstCrew(projects);

  return (
    <>
      <PageHead
        title="Crews"
        subtitle={`${String(crewCount(projects))} across ${String(projects.length)} projects`}
      />
      <div className="flex min-h-0 flex-1 overflow-hidden rounded-md border border-line bg-card">
        <div className="flex w-[204px] shrink-0 flex-col border-r border-line">
          <CrewRail projects={projects} selected={crew?.subject ?? null} onSelect={setPicked} />
        </div>
        {crew === null ? (
          <p className="m-0 grid flex-1 place-content-center p-6 text-sm text-muted">
            This company has no crew seats yet. Add one on the Company page.
          </p>
        ) : (
          <>
            <div className="flex min-w-0 flex-1 flex-col">
              <Conversation crew={crew} />
            </div>
            <div className="flex w-[304px] shrink-0 flex-col">
              <Workspace
                projectKey={crew.projectKey}
                sessions={sessionsOfProject(sessions.get(crew.projectKey))}
              />
            </div>
          </>
        )}
      </div>
    </>
  );
}
