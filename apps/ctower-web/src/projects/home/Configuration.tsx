import { ExternalLink } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { Card, CardBody, CardHeader, CardTitle, Chip } from "../../ui/primitives";
import { Inert } from "../Inert";
import type { ProjectFacts } from "../read";

/**
 * What this project is, as the record holds it.
 *
 * Every row is either a fact the bundle carries or an affordance that says why
 * it carries none. A `ctower.project/v1` payload is a closed shape — a name, a
 * ticket prefix, a repository, the goals it serves — so the rows the reference
 * console fills from a wider record are drawn and are inert, with the reason on
 * them. Drawing an editable box over a field the record cannot keep would take
 * an operator's answer and drop it.
 *
 * Nothing here writes. Changing a recorded project means authoring a new
 * revision of its document through the same check-plan-apply the Projects
 * screen runs, and no screen does that yet; a control that cannot honour a
 * press is not drawn as though it could.
 */
export function Configuration({ project }: { readonly project: ProjectFacts }): ReactElement {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardBody className="space-y-0">
          <Row label="Name">{project.name}</Row>
          <Row label="Ticket prefix">
            {project.prefix ?? <span className="text-muted">Not recorded</span>}
          </Row>
          <Row label="Description">
            <Inert reason="A recorded project has nowhere to keep a description yet.">
              Not set
            </Inert>
          </Row>
          <Row label="Status">
            <Inert reason="A recorded project holds no status.">Not set</Inert>
          </Row>
          <Row label="Goals">
            <span className="flex flex-wrap items-center gap-1.5">
              {project.goals.map((goal) => (
                <Chip key={goal} tone="amber">
                  {goal}
                </Chip>
              ))}
              <Inert
                className="chip"
                reason="Changing which goals a project serves records a new revision of it. No screen authors one yet."
              >
                + Goal
              </Inert>
            </span>
          </Row>
          <Row label="Environment">
            <Inert reason="A recorded project carries no environment of its own.">Not set</Inert>
          </Row>
          <Row label="Created">
            <Inert reason="The bundle records what a project is, not when it was written.">
              Not recorded
            </Inert>
          </Row>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Codebase</CardTitle>
        </CardHeader>
        <CardBody className="space-y-0">
          <Row label="Repository">
            <Repository project={project} />
          </Row>
          <Row label="Local folder">
            <Inert reason="A recorded project has no local folder, and a browser cannot read one.">
              Not set
            </Inert>
          </Row>
        </CardBody>
      </Card>

      <Card className="border-danger/50">
        <CardHeader className="border-danger/50">
          <CardTitle className="text-danger">Danger zone</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-wrap items-center gap-3">
          <p className="m-0 min-w-0 flex-1 text-sm text-muted">
            Archiving hides a project from the rail and from every chooser. Nothing is deleted: the
            record only ever grows.
          </p>
          <Inert
            className="rounded-sm border border-danger/60 px-4 py-2 text-sm font-semibold"
            reason="Archiving records a superseding revision of this project. No screen authors one yet."
          >
            Archive project
          </Inert>
        </CardBody>
      </Card>
    </div>
  );
}

/**
 * Where the code is, as somewhere a person can actually go.
 *
 * A link when this console knows the forge's address, and the same words
 * without one when it does not. What never renders is the reference the record
 * keeps: `repository:` is machine syntax nobody typed.
 */
function Repository({ project }: { readonly project: ProjectFacts }): ReactElement {
  if (project.repository === null) {
    return <span className="text-muted">Not set</span>;
  }
  if (project.repositoryUrl === null) {
    return <>{project.repository}</>;
  }
  return (
    <a
      href={project.repositoryUrl}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1.5 text-fg underline decoration-line underline-offset-2 hover:decoration-amber"
    >
      <ExternalLink aria-hidden className="size-3.5 shrink-0 text-muted" />
      {project.repository}
    </a>
  );
}

function Row({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactNode;
}): ReactElement {
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-line py-2.5 last:border-b-0">
      <span className="w-32 shrink-0 text-2xs text-muted">{label}</span>
      <span className="min-w-0 flex-1 text-sm text-fg">{children}</span>
    </div>
  );
}
