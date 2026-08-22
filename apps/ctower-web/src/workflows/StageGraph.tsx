import type { ReactElement } from "react";
import { Card, CardBody, CardHeader, CardTitle, Chip, Mono } from "../ui/primitives";
import { cn } from "../ui/cn";
import { entering, leaving, order } from "./graph";
import type { StageFact, WorkflowFact } from "./read";

/**
 * The stages, in the order work moves through them.
 *
 * The strip is the one place on this surface where a shape is drawn rather than
 * a list, and it is drawn from the declared transitions — so an arrow on this
 * screen is a transition the record holds, never a hint that two stages are
 * adjacent in an array. A workflow whose stages are not joined up shows exactly
 * that.
 */
export function StageGraph({ workflow }: { readonly workflow: WorkflowFact }): ReactElement {
  const { path, rest } = order(workflow);

  return (
    <div className="space-y-4">
      {path.length === 0 ? null : <Strip path={path} entry={workflow.initialStage} />}

      {workflow.stages.length === 0 ? (
        <Card>
          <CardBody>
            <p className="m-0 text-sm text-muted">This workflow declares no stage.</p>
          </CardBody>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {path.map((stage) => (
            <StageCard key={stage.key} stage={stage} workflow={workflow} />
          ))}
        </div>
      )}

      {rest.length === 0 ? null : (
        <div className="space-y-3">
          <p className="m-0 text-xs text-muted">
            No declared transition reaches these from the entry stage.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {rest.map((stage) => (
              <StageCard key={stage.key} stage={stage} workflow={workflow} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** The conveyor: entry stage first, one arrow per declared transition followed. */
function Strip({
  path,
  entry,
}: {
  readonly path: readonly StageFact[];
  readonly entry: string | null;
}): ReactElement {
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-card px-3 py-2.5">
      {path.map((stage, index) => (
        <span key={stage.key} className="flex items-center gap-1.5">
          {index === 0 ? null : (
            <span aria-hidden className="text-muted">
              →
            </span>
          )}
          <span
            className={cn(
              "rounded-sm border border-line px-2 py-1",
              stage.key === entry ? "border-l-2 border-l-amber" : ""
            )}
          >
            <Mono className="text-fg">{stage.key}</Mono>
          </span>
        </span>
      ))}
    </div>
  );
}

function StageCard({
  stage,
  workflow,
}: {
  readonly stage: StageFact;
  readonly workflow: WorkflowFact;
}): ReactElement {
  const out = leaving(workflow.transitions, stage.key);
  const back = entering(workflow.transitions, stage.key);
  const failures = workflow.routes.filter((route) => route.from === stage.key);

  return (
    <Card>
      <CardHeader className="px-4 py-2.5">
        <CardTitle className="text-sm">
          <Mono className="text-sm text-fg">{stage.key}</Mono>
        </CardTitle>
        <span className="flex-1" />
        {stage.key === workflow.initialStage ? <Chip tone="amber">entry</Chip> : null}
        {stage.activityClass === null ? null : <Chip>{stage.activityClass}</Chip>}
      </CardHeader>
      <CardBody className="space-y-1.5 px-4 py-3">
        <Row label="runs as">
          {stage.roles.length === 0 ? (
            <span className="text-muted">no role declared</span>
          ) : (
            <span className="flex flex-wrap items-center gap-1.5">
              {stage.roles.map((role, index) => (
                <span key={`${role.plane}:${role.key}`} className="flex items-center gap-1.5">
                  {index === 0 ? null : (
                    <span aria-hidden className="text-muted">
                      ·
                    </span>
                  )}
                  <Mono className="text-muted" title={role.plane}>
                    {role.key}
                  </Mono>
                </span>
              ))}
            </span>
          )}
        </Row>
        <Row label="leaves to">
          {out.length === 0 ? (
            <span className="text-muted">nothing — work ends here</span>
          ) : (
            <span className="space-y-0.5">
              {out.map((transition) => (
                <span key={`${transition.to}:${transition.predicate ?? ""}`} className="block">
                  <Mono className="text-fg">{transition.to}</Mono>
                  {transition.predicate === null ? null : (
                    <>
                      <span className="text-muted"> when </span>
                      <Mono className="text-muted">{transition.predicate}</Mono>
                    </>
                  )}
                </span>
              ))}
            </span>
          )}
        </Row>
        {back.length === 0 ? null : (
          <Row label="entered from">
            <span className="flex flex-wrap items-center gap-1.5">
              {back.map((transition, index) => (
                <span key={transition.from} className="flex items-center gap-1.5">
                  {index === 0 ? null : (
                    <span aria-hidden className="text-muted">
                      ·
                    </span>
                  )}
                  <Mono className="text-muted">{transition.from}</Mono>
                </span>
              ))}
            </span>
          </Row>
        )}
        {failures.length === 0 ? null : (
          <Row label="on failure">
            <span className="space-y-0.5">
              {failures.map((route) => (
                <span key={`${route.failureClass ?? ""}:${route.to}`} className="block">
                  <Mono className="text-muted">{route.failureClass ?? "any"}</Mono>
                  <span className="text-muted"> → </span>
                  <Mono className="text-fg">{route.to}</Mono>
                </span>
              ))}
            </span>
          </Row>
        )}
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
