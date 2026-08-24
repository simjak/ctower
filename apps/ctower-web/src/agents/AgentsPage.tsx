import { Plus } from "lucide-react";
import type { ReactElement } from "react";
import type { CompanyBundleExportResult } from "@ctower/client";
import { Button, PageHead } from "../ui/primitives";
import { useCeremony } from "../wizard/ceremony";
import { ReviewPanel } from "../wizard/review/ReviewPanel";
import { AgentHome } from "./AgentHome";
import { AgentList } from "./AgentList";
import { NewAgent } from "./NewAgent";
import { agentAt, agentsOf } from "./roster";

const PURPOSE = "Who works for this company. Open one to see what it has done.";

/**
 * Agents: the company's own, and one more.
 *
 * This screen is a junction rather than a page — the address decides which of
 * three things is drawn, and each of them is a different question. Naming an
 * agent opens that agent's home; making one opens the pop-up over the list;
 * proposing either sends the whole screen to the one review this console has.
 *
 * There is no `createAgent` operation and there is not meant to be one. An
 * agent is two components of the company bundle, so making one is authoring
 * documents into the recorded bundle and handing the result to the same
 * check-plan-apply every other authoring screen runs.
 *
 * **Lane seam.** The list body is `AgentList` and it is deliberately the
 * smallest honest one: the agents this company records, and the way in to each.
 * §2's own screen — the filter tabs, "See all", the rail's AGENTS section — is
 * the agents-page lane's, and it replaces that one file without touching this
 * junction, the home, or the create flow.
 */
export function AgentsPage({
  result,
  opened,
  creating,
  onCreating,
  onOpen,
  onBack,
  onApplied,
}: {
  readonly result: CompanyBundleExportResult;
  /** The agent whose own screen the address names, when it names one. */
  readonly opened: string | null;
  /** Whether the pop-up that makes an agent is open. */
  readonly creating: boolean;
  readonly onCreating: (creating: boolean) => void;
  /** Opening an agent is a place: the address reopens on it. */
  readonly onOpen: (key: string) => void;
  readonly onBack: () => void;
  readonly onApplied: () => void;
}): ReactElement {
  const ceremony = useCeremony(result.bundle, onApplied);
  const open = agentAt(result.bundle, opened);

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
        backLabel="Back to agents"
      />
    );
  }

  // An address naming an agent this company no longer records falls back to the
  // list rather than to a blank screen: the agent is gone, and the list is the
  // true answer to where it went.
  if (open !== null) {
    return <AgentHome agent={open} onBack={onBack} />;
  }

  return (
    <>
      <PageHead title="Agents" subtitle={PURPOSE}>
        <Button
          variant="primary"
          onClick={(): void => {
            onCreating(true);
          }}
        >
          <Plus /> New agent
        </Button>
      </PageHead>
      <AgentList agents={agentsOf(result.bundle)} onOpen={onOpen} />
      <NewAgent
        authoring={ceremony.authoring}
        company={result.bundle.company.display_name}
        open={creating}
        onOpenChange={onCreating}
      />
    </>
  );
}
