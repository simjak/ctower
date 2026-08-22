import { Plus } from "lucide-react";
import type { ReactElement } from "react";
import type { CompanyBundleExportResult } from "@ctower/client";
import { Button, Card, CardBody, Chip, Mono, PageHead } from "../ui/primitives";
import { cn } from "../ui/cn";
import { shortDigest } from "../wizard/bundle";
import { ReviewPanel } from "../wizard/review/ReviewPanel";
import { Editor, EditorFooter } from "./Editor";
import { WorkflowCard } from "./WorkflowCard";
import { useWorkflows } from "./useWorkflows";
import type { WorkflowFact } from "./read";

/**
 * The Workflows page.
 *
 * A workflow is not a thing the API serves on its own — it is a component of
 * the company definition, and the definition is what this console already read.
 * So the page costs no call to look at, and changing one is the bundle's own
 * ceremony: check, plan, and a command that runs with the operator's authority.
 *
 * The page is what the record holds and nothing beside it. A company with no
 * workflow says so and offers the one thing that changes that; a workflow with
 * no moves declared draws no arrows.
 */
const PURPOSE = "The stages work moves through, and the rules each one runs under.";

export function WorkflowsPage({
  seed,
  onApplied,
}: {
  readonly seed: CompanyBundleExportResult;
  readonly onApplied: () => void;
}): ReactElement {
  const page = useWorkflows(seed.bundle, onApplied);

  if (page.mode === "review") {
    return (
      <ReviewPanel
        review={page.review}
        applied={page.applied}
        armed={page.armed}
        onArm={page.setArmed}
        onApply={page.apply}
        onRetry={page.retry}
        onBack={page.closeReview}
        backLabel="Back to the workflow"
      />
    );
  }

  if (page.mode === "edit" && page.draft !== null) {
    const draft = page.draft;
    return (
      <>
        <PageHead
          title={draft.base === null ? "Add a workflow" : `Change ${draft.base.key}`}
          subtitle={PURPOSE}
        >
          {draft.base === null ? null : (
            <Mono className="text-muted">
              r{draft.base.revision} → r{draft.base.revision + 1}
            </Mono>
          )}
          <Chip>not checked</Chip>
        </PageHead>
        <Editor draft={draft} onDraft={page.setDraft} document={seed.bundle} />
        <EditorFooter edits={page.edits} onCancel={page.cancel} onReview={page.openReview} />
      </>
    );
  }

  return (
    <>
      <PageHead title="Workflows" subtitle={PURPOSE}>
        <Chip>{page.declared.length} declared</Chip>
        <span className="text-sm text-muted">
          version <Mono>{seed.active_version}</Mono>
        </span>
        <Mono className="text-muted" title={seed.bundle_digest}>
          {shortDigest(seed.bundle_digest)}
        </Mono>
      </PageHead>

      {page.declared.length > 1 ? (
        <Chooser declared={page.declared} here={page.here} onChoose={page.select} />
      ) : null}

      {page.here === null ? (
        <Card>
          <CardBody>
            <p className="m-0 text-sm text-muted">This company declares no workflow yet.</p>
          </CardBody>
        </Card>
      ) : (
        <WorkflowCard workflow={page.here} document={seed.bundle} />
      )}

      <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
        <span className="flex-1" />
        <Button variant={page.here === null ? "primary" : "ghost"} onClick={page.add}>
          <Plus /> Add a workflow
        </Button>
        {page.here === null ? null : (
          <Button variant="primary" onClick={page.revise}>
            Change this workflow
          </Button>
        )}
      </footer>
    </>
  );
}

/** Which workflow is being read, when a company declares more than one. */
function Chooser({
  declared,
  here,
  onChoose,
}: {
  readonly declared: readonly WorkflowFact[];
  readonly here: WorkflowFact | null;
  readonly onChoose: (id: string) => void;
}): ReactElement {
  return (
    <div className="mb-3 flex flex-wrap gap-2" role="tablist" aria-label="Declared workflows">
      {declared.map((workflow) => (
        <Button
          key={workflow.id}
          size="sm"
          variant="ghost"
          role="tab"
          aria-selected={workflow.id === here?.id}
          className={cn("font-mono", workflow.id === here?.id ? "border-amber bg-amber/14" : "")}
          onClick={(): void => {
            onChoose(workflow.id);
          }}
        >
          {workflow.key}
        </Button>
      ))}
    </div>
  );
}
