import { Plus } from "lucide-react";
import type { ReactElement } from "react";
import type { CompanyBundleExportResult } from "@ctower/client";
import type { DestinationKey } from "../shell/destinations";
import { Button, PageHead } from "../ui/primitives";
import { useCeremony } from "../wizard/ceremony";
import { ReviewPanel } from "../wizard/review/ReviewPanel";
import { NewProject } from "./NewProject";
import { ProjectCard } from "./ProjectCard";
import { goalRefsIn, projectsIn } from "./read";
import { useBoards } from "./useBoards";

const PURPOSE = "What this company builds. Open one to work in it.";

/**
 * Projects: the ones this company has, and one more.
 *
 * This is the company workspace's own screen, and the only place a project is
 * made. A project is not a runtime and it is not a harness: it is a thing the
 * company has, so it is listed beside the company rather than beside the
 * machinery its work runs on.
 *
 * The cards cost no read — the active bundle answered before this screen
 * existed — but what is *happening* on each project is that project's own board,
 * and those answers arrive one at a time and land on their own card.
 *
 * There is no `createProject` operation and there is not meant to be one. A
 * project is a component of the company bundle, so making one is authoring a
 * document into the recorded bundle and handing the result to the same
 * check-plan-apply every other authoring screen runs.
 */
export function ProjectsPage({
  result,
  creating,
  onCreating,
  onApplied,
  onGo,
}: {
  readonly result: CompanyBundleExportResult;
  /** Whether the pop-up that makes a project is open. */
  readonly creating: boolean;
  readonly onCreating: (creating: boolean) => void;
  readonly onApplied: () => void;
  /** Opening a project scopes the whole project workspace to it. */
  readonly onGo: (key: DestinationKey) => void;
}): ReactElement {
  const ceremony = useCeremony(result.bundle, onApplied);
  const projects = projectsIn(result.bundle);
  const boards = useBoards(projects.map((project) => project.key));

  if (ceremony.review !== null) {
    return (
      <ReviewPanel
        review={ceremony.review}
        applied={ceremony.applied}
        armed={ceremony.armed}
        onArm={ceremony.setArmed}
        onApply={ceremony.apply}
        onRetry={ceremony.retry}
        onBack={ceremony.close}
        backLabel="Back to projects"
      />
    );
  }

  return (
    <>
      <PageHead title="Projects" subtitle={PURPOSE}>
        <Button
          variant="primary"
          onClick={(): void => {
            onCreating(true);
          }}
        >
          <Plus /> New project
        </Button>
      </PageHead>

      {projects.length === 0 ? (
        <Nothing onNew={onCreating} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard
              key={project.key}
              project={project}
              board={boards.get(project.key) ?? { kind: "asking" }}
              here={false}
              onOpen={(): void => {
                onGo("tickets");
              }}
            />
          ))}
        </div>
      )}

      <NewProject
        authoring={ceremony.authoring}
        goals={goalRefsIn(result.bundle)}
        company={result.bundle.company.display_name}
        open={creating}
        onOpenChange={onCreating}
      />
    </>
  );
}

/**
 * A company with no project at all. It is a real state and not a broken one,
 * and the one action that changes it sits next to the sentence that says so.
 */
function Nothing({ onNew }: { readonly onNew: (creating: boolean) => void }): ReactElement {
  return (
    <div className="rounded-md border border-line bg-raised p-4">
      <p className="m-0 text-sm text-fg">This company has no project yet.</p>
      <Button
        variant="primary"
        className="mt-3"
        onClick={(): void => {
          onNew(true);
        }}
      >
        <Plus /> New project
      </Button>
    </div>
  );
}
