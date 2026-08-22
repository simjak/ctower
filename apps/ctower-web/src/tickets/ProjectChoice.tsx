import { useState } from "react";
import type { ReactElement } from "react";
import { Field } from "../ui/form";
import { Button, Card, CardBody, Input, Mono, PageHead } from "../ui/primitives";
import type { WorkProject } from "./projects";

/**
 * Which board to read, when the address does not say.
 *
 * One project opens without asking; several ask, because picking the
 * alphabetically first would be a guess dressed as a default. The choices come
 * from the company definition's own project components, and any other key can
 * still be named — no operation the authored contract declares enumerates
 * work-plane projects, so a list here can only be an offer, never the whole
 * truth.
 */
export function ProjectChoice({
  projects,
  onChoose,
}: {
  readonly projects: readonly WorkProject[];
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
              This company defines no project, so there is no board to offer.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {projects.map((project) => (
                <Button
                  key={project.key}
                  onClick={(): void => {
                    onChoose(project.key);
                  }}
                >
                  {project.name}
                  <Mono className="text-muted">{project.key}</Mono>
                </Button>
              ))}
            </div>
          )}
          <div className="flex items-end gap-3 border-t border-line pt-4">
            <div className="min-w-0 flex-1">
              <Field label="OR NAME ONE" hint="A work-plane project key, as the record spells it.">
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
