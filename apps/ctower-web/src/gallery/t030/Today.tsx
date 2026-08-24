import { ExternalLink } from "lucide-react";
import type { ReactElement } from "react";
import { Card, CardBody, CardHeader, CardTitle, Chip } from "../../ui/primitives";
import { GOALS, HERE, REPOSITORY } from "./fixtures";
import { Row } from "./Marks";

/**
 * The same tab, honest, before the contract moves — and this is the screen that
 * should ship first.
 *
 * The operator's finding on the walk was that Description, Status, Environment
 * and Created all render `Not set` because a `ctower.project/v1` payload has
 * nowhere to keep any of them, and that a page of them reads as broken. His
 * ruling: *either the fields enter the schema, or the rows do not render.*
 *
 * So they do not render. Not dimmed, not inert, not a dashed placeholder —
 * **absent**, along with the environment card and the archive zone, because an
 * archive nothing can perform is the same lie in a red box. What is left is the
 * four things a recorded project is, and one muted line naming what it is not.
 * Seven dead rows become one sentence, and the operator learns the same fact in
 * a tenth of the space.
 *
 * The rows come back the day the record can hold them, and not one day before.
 */
export function Today(): ReactElement {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardBody className="space-y-0 py-1">
          <Row label="Name">{HERE.name}</Row>
          <Row label="Ticket prefix">{HERE.prefix}</Row>
          <Row label="Goals">
            <span className="flex flex-wrap items-center gap-1.5">
              {GOALS.map((goal) => (
                <Chip key={goal} tone="amber">
                  {goal}
                </Chip>
              ))}
            </span>
          </Row>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Codebase</CardTitle>
        </CardHeader>
        <CardBody className="space-y-0 py-1">
          <Row label="Repository">
            <a
              href={REPOSITORY.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-fg underline decoration-line underline-offset-2 hover:decoration-amber"
            >
              <ExternalLink aria-hidden className="size-3.5 shrink-0 text-muted" />
              {REPOSITORY.label}
            </a>
          </Row>
        </CardBody>
      </Card>

      <p className="m-0 text-2xs text-muted">
        This is everything a project is recorded as today. Describing one, giving it a status, its
        own variables or an archive comes with the next version of the record.
      </p>
    </div>
  );
}
