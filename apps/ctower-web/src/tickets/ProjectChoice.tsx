import { useState } from "react";
import type { ReactElement } from "react";
import { Field } from "../ui/form";
import { Button, Card, CardBody, Input, PageHead } from "../ui/primitives";

const NAMED =
  "A work-plane project key, as the record spells it. A key the work plane does not know answers exactly as an empty project does.";

/**
 * Which board to read, when the address does not say.
 *
 * The choices are the project scopes this company's components declare
 * themselves to belong to — the identifier `getBoard` takes — and they carry no
 * name, because the names live in project documents and nothing records a join
 * from one to the other. Any other key can still be named: no operation the
 * authored contract declares enumerates work-plane projects, so a list here can
 * only be an offer, never the whole truth.
 */
export function ProjectChoice({
  projects,
  onChoose,
}: {
  readonly projects: readonly string[];
  readonly onChoose: (projectKey: string) => void;
}): ReactElement {
  const [named, setNamed] = useState("");

  return (
    <>
      <PageHead title="Tickets" subtitle="Which project's tickets?" />
      <Card>
        <CardBody className="space-y-4">
          {projects.length === 0 ? (
            <p className="m-0 text-sm text-muted">
              Nothing in this company is scoped to a project, so there is no board to offer.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {projects.map((project) => (
                <Button
                  key={project}
                  className="mono"
                  onClick={(): void => {
                    onChoose(project);
                  }}
                >
                  {project}
                </Button>
              ))}
            </div>
          )}
          <div className="flex items-end gap-3 border-t border-line pt-4">
            <div className="min-w-0 flex-1">
              <Field label="OR NAME ONE" hint={NAMED}>
                <Input
                  aria-label="Project key"
                  className="mono"
                  value={named}
                  onChange={(event): void => {
                    setNamed(event.target.value);
                  }}
                />
              </Field>
            </div>
            <Button
              disabled={named.trim() === ""}
              onClick={(): void => {
                onChoose(named.trim());
              }}
            >
              Open it
            </Button>
          </div>
        </CardBody>
      </Card>
    </>
  );
}
