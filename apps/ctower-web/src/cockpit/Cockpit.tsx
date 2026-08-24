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
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-line bg-card lg:flex-row">
        <div className="flex min-h-0 shrink-0 flex-col border-line max-lg:max-h-[40%] max-lg:border-b lg:w-[204px] lg:border-r">
          <CrewRail projects={projects} selected={crew?.subject ?? null} onSelect={setPicked} />
        </div>
        {crew === null ? (
          <p className="m-0 grid flex-1 place-content-center p-6 text-sm text-muted">
            This company has no crew seats yet. Add one on the Company page.
          </p>
        ) : (
          <>
            {/* The rail is 204 and the workspace 304, so under 1024 the two of
                them have already spent the row and the conversation between
                them is handed a width of nothing. A pane of zero width does not
                disappear — it overlaps its neighbour and both become
                unreadable, which is a screen asserting facts the operator
                cannot check. So below that width the two panes say they are not
                drawn and why, and the roster stays, because it is a real read
                that fits. */}
            <p className="m-0 grid flex-1 place-content-center p-6 text-center text-sm text-balance text-muted lg:hidden">
              This crew's conversation and workspace need a wider window.
            </p>
            <div className="flex min-w-0 flex-1 flex-col max-lg:hidden">
              <Conversation crew={crew} />
            </div>
            <div className="flex w-[304px] shrink-0 flex-col max-lg:hidden">
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
