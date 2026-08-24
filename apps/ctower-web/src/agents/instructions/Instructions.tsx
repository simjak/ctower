import { useCallback, useState } from "react";
import type { ReactElement } from "react";
import type { CompanyBundleDocument } from "@ctower/client";
import { Card, CardBody } from "../../ui/primitives";
import { ReviewPanel } from "../../wizard/review/ReviewPanel";
import { useSeed } from "../../wizard/useSeed";
import { Waiting } from "../Waiting";
import { agentIn } from "./agent";
import type { Agent } from "./agent";
import { FileEditor } from "./FileEditor";
import { FileList } from "./FileList";
import { useAgentFiles } from "./useAgentFiles";

/**
 * What one agent is told, and the one way to change it.
 *
 * This surface used to be a tab on the harness screen called "Agent files",
 * where it listed every persona, skill and tool the company carried. That was
 * the wrong shelf twice over: a harness is a runtime and has no opinion about
 * what an agent reads, and a list of everything is not an answer to what *this*
 * agent is told. Here it is one agent's own — resolved through the profile's
 * `persona_ref`, `skill_refs` and `tool_refs` — and the harness screen no
 * longer carries it.
 *
 * Nothing underneath changed. There is no filesystem-file operation in the
 * authored contract and this screen still does not invent one: a persona, a
 * skill and a tool are components of the company definition, so editing one is
 * editing the company under the same check, the same plan and the same command
 * the first-run wizard performs.
 *
 * It reads the company for itself, so it mounts on one prop. A host that also
 * read the bundle is a version behind the moment an apply is accepted — the
 * operator's own edit is what made it stale — so `onApplied` fires on
 * acceptance and only on acceptance. A host with nothing to re-read may omit
 * it; this surface still refreshes itself.
 */
export function Instructions({
  agentKey,
  onApplied,
}: {
  /** The agent profile's key. It travels through the address; it never renders. */
  readonly agentKey: string;
  /** An accepted apply changed what is recorded; a host that reads should re-read. */
  readonly onApplied?: () => void;
}): ReactElement {
  const [reloadKey, setReloadKey] = useState(0);
  const seed = useSeed(reloadKey);
  const reread = useCallback((): void => {
    setReloadKey((count) => count + 1);
    onApplied?.();
  }, [onApplied]);

  if (seed.kind !== "answered") {
    return <Waiting answer={seed} what="Reading what this agent is told" />;
  }
  if (seed.value.kind === "template") {
    return <Nothing said="This tower has no company yet, so no agent has been told anything." />;
  }
  const document = seed.value.result.bundle;
  const agent = agentIn(document, agentKey);
  if (agent === null) {
    return <Nothing said="This company carries no agent by that name." />;
  }
  return <Told document={document} agent={agent} onApplied={reread} />;
}

/** The header note the operator asked for, on every mode and every file. */
const WHEN =
  "Saved instructions affect the next run. Active runs keep the instructions they started with.";

function Told({
  document,
  agent,
  onApplied,
}: {
  readonly document: CompanyBundleDocument;
  readonly agent: Agent;
  readonly onApplied: () => void;
}): ReactElement {
  const files = useAgentFiles(document, onApplied);

  if (files.mode === "review") {
    return (
      <ReviewPanel
        review={files.review}
        applied={files.applied}
        armed={files.armed}
        onArm={files.setArmed}
        onApply={files.apply}
        onRetry={files.retry}
        onBack={files.closeReview}
        backLabel="Back to the file"
      />
    );
  }

  if (agent.files.length === 0) {
    return (
      <Nothing said="This agent is told nothing yet: its profile names no persona, skill or tool." />
    );
  }

  return (
    <div className="space-y-4">
      <p className="m-0 text-sm text-muted">{WHEN}</p>
      <div className="grid gap-4 md:grid-cols-[260px_minmax(0,1fr)]">
        <FileList files={agent.files} openId={files.openId} onOpen={files.open} />
        {files.draft === null ? (
          <Nothing said="Choose what this agent reads, on the left." />
        ) : (
          <FileEditor
            document={document}
            draft={files.draft}
            onDraft={files.setDraft}
            edited={files.edited}
            onReview={files.openReview}
          />
        )}
      </div>
    </div>
  );
}

function Nothing({ said }: { readonly said: string }): ReactElement {
  return (
    <Card>
      <CardBody>
        <p className="m-0 text-sm text-muted">{said}</p>
      </CardBody>
    </Card>
  );
}
