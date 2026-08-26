import type { ReactElement, ReactNode } from "react";
import { RepositoryLink } from "../../repository/RepositoryLink";
import { Card, CardBody, CardHeader, CardTitle, Chip } from "../../ui/primitives";
import type { ProjectFacts } from "../read";

/**
 * What this project is, as the record holds it — and nothing else.
 *
 * A recorded project is a closed shape: a name, a ticket prefix, the goals it
 * serves, the repository its work belongs to. This tab used to draw the
 * reference console's whole configuration screen over that shape and mark the
 * seven fields the record has nowhere to keep as inert. The operator read the
 * result as a broken page rather than as an honest one, and he was right: one
 * inert control among live ones says *not yet*, and a card of them says *this
 * screen does not work*.
 *
 * So a row renders exactly when the bundle answers it, and is **absent**
 * otherwise — not dimmed, not dashed, not `Not set`. Under the cards, one
 * muted line names what a project cannot yet record, which is the same fact in
 * a tenth of the space and without a single dead affordance. The rows come back
 * the day the record can hold them.
 *
 * Nothing here writes. Changing a recorded project authors a new revision of
 * its document through the same check-plan-apply the Projects screen runs, and
 * no screen does that yet — so this tab offers no control at all rather than
 * one that cannot honour a press.
 */
export function Configuration({ project }: { readonly project: ProjectFacts }): ReactElement {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardBody className="space-y-0 py-1">
          <Row label="Name">{project.name}</Row>
          {project.prefix === null ? null : <Row label="Ticket prefix">{project.prefix}</Row>}
          {project.goals.length === 0 ? null : (
            <Row label="Goals">
              <span className="flex flex-wrap items-center gap-1.5">
                {project.goals.map((goal) => (
                  <Chip key={goal} tone="amber">
                    {goal}
                  </Chip>
                ))}
              </span>
            </Row>
          )}
        </CardBody>
      </Card>

      {project.repository === null ? null : (
        <Card>
          <CardHeader>
            <CardTitle>Codebase</CardTitle>
          </CardHeader>
          <CardBody className="space-y-0 py-1">
            <Row label="Repository">
              {/* Where the code is, as somewhere a person can actually go: the
                  repository's own name, its forge's mark, and the way to it.
                  What never renders is the reference the record keeps —
                  `repository:` is machine syntax nobody typed. */}
              <RepositoryLink repository={project.repository} className="text-fg" />
            </Row>
          </CardBody>
        </Card>
      )}

      <p className="m-0 text-2xs text-muted">{WAITING}</p>
    </div>
  );
}

/**
 * The one line that replaced seven dead rows.
 *
 * It names the four things the reference console configures here and this
 * record cannot yet hold, without drawing a row, a control or a promise for any
 * of them. Archiving sits in the same sentence as the rest and for the same
 * reason: this company's registry answers every plan that retires a component
 * with a refusal, so an archive control could only ever build a document
 * nothing will accept.
 */
const WAITING =
  "This is everything a project is recorded as today. A description, a status, its own variables and archiving one all wait on a record that can hold them.";

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
