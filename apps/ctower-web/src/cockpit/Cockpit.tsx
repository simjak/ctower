import { useMemo } from "react";
import type { ReactElement } from "react";
import { cn } from "../ui/cn";
import { Conversation } from "./Conversation";
import { NARROW, PANES, WORKSPACE } from "./panes";
import type { Crew, Project } from "./roster";
import { sessionsOfProject, useSessions } from "./useSessions";
import { Workspace } from "./Workspace";

/**
 * The cockpit: the conversation with the selected crew, and that crew's
 * workspace beside it. The crews themselves are in the shell's rail, under the
 * destinations — one rail, the way the reference has it.
 *
 * Exactly two surfaces here carry a real read: the roster the rail draws is the
 * active company bundle, and the work on the right is that project's recorded
 * sessions. The transcript, the composer, the steer control and the terminal
 * are drawn as absent, because the operations behind them either have no
 * implementation at this head or answer on a surface this browser is not — and
 * a pane that pretends is worse than a pane that says so.
 */
export function Cockpit({
  projects,
  crew,
}: {
  readonly projects: readonly Project[];
  readonly crew: Crew | null;
}): ReactElement {
  const sessions = useSessions(useMemo(() => projects.map((p) => p.key), [projects]));

  return (
    <>
      <NeedsRoom />
      {/* No page head. The reference puts its panes straight under the window
          chrome, and the breadcrumb in the centre is what orients you — a title
          bar over the top would be a row the reference does not have. */}
      <div
        className={cn(
          PANES,
          "min-h-0 flex-1 overflow-hidden rounded-md border border-line bg-card"
        )}
      >
        {crew === null ? (
          <p className="m-0 grid flex-1 place-content-center p-6 text-sm text-muted">
            This company has no crew seats yet. Add one on the Company page.
          </p>
        ) : (
          <>
            <div className="flex min-w-0 flex-1 flex-col">
              <Conversation crew={crew} />
            </div>
            <div className={cn(WORKSPACE, "flex shrink-0 flex-col")}>
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

/**
 * The window is too narrow for the panes, so it says that instead of drawing
 * them into each other.
 *
 * The right pane is a measured fixed width and the centre takes the remainder;
 * below 1024 that remainder runs out, and the earlier build let it reach zero —
 * a pane with no width, clipping controls a keyboard could still reach but an
 * eye could not find. This is the state the design file promised and did not
 * draw. It is not an unbuilt surface and it carries no `(i)`: the cockpit is
 * built, and the only fact worth saying is the one an operator can act on.
 */
function NeedsRoom(): ReactElement {
  return (
    <div className={cn(NARROW, "grid flex-1 place-content-center p-6 text-center")}>
      <div className="max-w-[42ch]">
        <p className="m-0 text-sm font-medium">Needs a wider window</p>
        <p className="mt-1 mb-0 text-xs text-balance text-muted">
          The cockpit's panes need 1024px across; widen this window to open a crew.
        </p>
      </div>
    </div>
  );
}
