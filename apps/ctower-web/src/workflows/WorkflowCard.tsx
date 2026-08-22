import { useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { Button, Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { cn } from "../ui/cn";
import { shortDigest } from "../wizard/bundle";
import { boundProjects } from "./compose";
import { Rules } from "./Rules";
import { StageGraph } from "./StageGraph";
import type { WorkflowFact } from "./read";

/**
 * One declared workflow, and the two ways to read it.
 *
 * *Stages* is the product: what work moves through and what it runs under.
 * *Source* is the record: the exact authored document the digest above it is
 * taken over. Both are the same fact and neither is a rendering of the other,
 * which is why the source is offered at all — an operator who wants to check
 * what is recorded should not have to trust this page's reading of it.
 *
 * Two publication facts sit on this card and they are not merged. A workflow
 * declares its own state, and the component carrying it has a state in the
 * registry. They can differ — a published component can carry a staged
 * workflow, which is exactly what this tower holds — and a console that showed
 * one chip would be choosing which of the two to hide.
 */
export function WorkflowCard({
  workflow,
  document,
}: {
  readonly workflow: WorkflowFact;
  readonly document: CompanyBundleDocument;
}): ReactElement {
  const [reading, setReading] = useState<"stages" | "source">("stages");
  const projects = boundProjects(document, workflow.key);

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle>
            <Mono className="text-md text-fg">{workflow.key}</Mono>
          </CardTitle>
          <span className="flex-1" />
          <Toggle reading={reading} onRead={setReading} />
        </CardHeader>
        <CardBody className="space-y-1.5">
          <Row label="publication">
            {workflow.status === null ? (
              <span className="text-muted">not declared</span>
            ) : (
              <Chip>{workflow.status}</Chip>
            )}
          </Row>
          <Row label="in the record">
            <span className="flex items-center gap-2">
              <Chip>{workflow.lifecycle}</Chip>
              <Mono className="text-muted">r{workflow.revision}</Mono>
              <Mono className="text-muted" title={workflow.digest}>
                {shortDigest(workflow.digest)}
              </Mono>
            </span>
          </Row>
          <Row label="runs on">
            {projects.length === 0 ? (
              <span className="text-muted">no project is bound to it</span>
            ) : (
              <span className="flex flex-wrap items-center gap-1.5">
                {projects.map((project, index) => (
                  <span key={project} className="flex items-center gap-1.5">
                    {index === 0 ? null : (
                      <span aria-hidden className="text-muted">
                        ·
                      </span>
                    )}
                    <Mono className="text-fg">{project}</Mono>
                  </span>
                ))}
              </span>
            )}
          </Row>
          {workflow.note === null ? null : (
            <Row label="note">
              <span className="text-muted">{workflow.note}</span>
            </Row>
          )}
        </CardBody>
      </Card>

      {reading === "stages" ? (
        <>
          <StageGraph workflow={workflow} />
          <Rules workflow={workflow} document={document} />
        </>
      ) : (
        <Source workflow={workflow} />
      )}
    </div>
  );
}

function Toggle({
  reading,
  onRead,
}: {
  readonly reading: "stages" | "source";
  readonly onRead: (reading: "stages" | "source") => void;
}): ReactElement {
  return (
    <span className="flex overflow-hidden rounded-sm border border-line">
      {(["stages", "source"] as const).map((name) => (
        <Button
          key={name}
          size="sm"
          variant="quiet"
          aria-pressed={reading === name}
          className={cn("rounded-none", reading === name ? "bg-amber/14 text-fg" : "")}
          onClick={(): void => {
            onRead(name);
          }}
        >
          {name}
        </Button>
      ))}
    </span>
  );
}

/** The authored document, as the record holds it. Nothing is reformatted away. */
function Source({ workflow }: { readonly workflow: WorkflowFact }): ReactElement {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Source</CardTitle>
        <span className="flex-1" />
        <Mono className="text-muted">{workflow.schemaRef}</Mono>
      </CardHeader>
      <CardBody>
        <pre className="m-0 overflow-x-auto rounded-sm border border-line bg-bg p-3 font-mono text-xs leading-relaxed text-fg">
          {JSON.stringify(workflow.payload, null, 2)}
        </pre>
      </CardBody>
    </Card>
  );
}

function Row({
  label,
  children,
}: {
  readonly label: string;
  readonly children: ReactElement;
}): ReactElement {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-24 shrink-0 text-2xs text-muted">{label}</span>
      <span className="min-w-0 flex-1 text-sm">{children}</span>
    </div>
  );
}
